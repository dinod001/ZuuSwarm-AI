import { useState, useCallback, useRef } from 'react';

export type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

export type StreamStatus = {
  active: boolean;
  stageLabel: string;
};

export function useChatStream(userId: string, sessionId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<StreamStatus>({ active: false, stageLabel: '' });
  const streamBuf = useRef('');

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim()) return;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    streamBuf.current = '';

    setStatus({ active: true, stageLabel: 'Connecting...' });

    try {
      const startTime = Date.now();
      const response = await fetch('http://localhost:8000/api/v1/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          user_id: userId,
          session_id: sessionId,
          message: text,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      if (!response.body) {
        throw new Error('ReadableStream not supported.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      const processEvent = (raw: string) => {
        const lines = raw.split('\n');
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.substring(6).trim();
          if (!jsonStr) continue;

          try {
            const data = JSON.parse(jsonStr);
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
            console.log(`[SSE @ ${elapsed}s]`, data.type, data.label || data.stage || '');

            switch (data.type) {
              case 'stage_start':
                if (data.label) {
                  setStatus({ active: true, stageLabel: data.label });
                }
                break;
              case 'stage_done':
                break;
              case 'token': {
                const chunk = data.content ?? '';
                streamBuf.current += chunk;
                const snap = streamBuf.current;
                setMessages(prev => {
                  const last = prev[prev.length - 1];
                  if (last && last.id === '__streaming__') {
                    return [...prev.slice(0, -1), { ...last, content: snap }];
                  }
                  return [...prev, { id: '__streaming__', role: 'assistant', content: snap }];
                });
                break;
              }
              case 'final': {
                const answer = data.answer || streamBuf.current || 'No response.';
                setMessages(prev => {
                  const clean = prev.filter(m => m.id !== '__streaming__');
                  return [...clean, { id: `ans-${Date.now()}`, role: 'assistant', content: answer }];
                });
                setStatus({ active: false, stageLabel: '' });
                streamBuf.current = '';
                break;
              }
              case 'error':
                setStatus({ active: false, stageLabel: `Error: ${data.message || 'Unknown error'}` });
                streamBuf.current = '';
                break;
            }
          } catch {
            console.warn('[SSE] unparseable:', jsonStr);
          }
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        const readTime = ((Date.now() - startTime) / 1000).toFixed(2);
        console.log(`[Network Read @ ${readTime}s] Received ${value?.byteLength || 0} bytes`);
        
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split(/\r?\n\r?\n/);
        buffer = events.pop() || '';

        for (const evt of events) {
          if (evt.trim()) {
            processEvent(evt);
            
            // If the browser buffers chunks and returns them all at once, 
            // we MUST add a delay here so the user can actually see them, 
            // otherwise they overwrite in a single frame.
            const isStage = evt.includes('"type":"stage_start"') || evt.includes('"type": "stage_start"');
            if (isStage) {
               await new Promise(r => setTimeout(r, 800)); 
            } else {
               await new Promise(r => setTimeout(r, 0));
            }
          }
        }
      }

      if (buffer.trim()) {
        processEvent(buffer);
      }

      setStatus(prev => (prev.active ? { active: false, stageLabel: '' } : prev));

    } catch (error) {
      console.error('[SSE] Stream error:', error);
      setStatus({ active: false, stageLabel: '' });
    }
  }, [userId, sessionId]);

  return { messages, status, sendMessage };
}
