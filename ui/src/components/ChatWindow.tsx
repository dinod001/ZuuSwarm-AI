import React, { useEffect, useRef } from 'react';
import { useChatStream } from '../hooks/useChatStream';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';

interface ChatWindowProps {
  userId: string;
  sessionId: string;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ userId, sessionId }) => {
  const { messages, status, sendMessage } = useChatStream(userId, sessionId);
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on every change
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, status.stageLabel]);

  return (
    <div className="chat-container">
      <div className="message-list" ref={listRef}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)', marginTop: '2rem' }}>
            <h2>Welcome to ZuuSwarm AI</h2>
            <p>I can help with IT Ops, access requests, and system health.</p>
          </div>
        )}
        
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {status.active && status.stageLabel && (
          <div className="agent-status">
            <div className="pulse-dot"></div>
            <span>{status.stageLabel}</span>
          </div>
        )}
      </div>
      
      <ChatInput onSend={sendMessage} disabled={status.active} />
    </div>
  );
};
