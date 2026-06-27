import React, { useEffect, useRef } from 'react';
import { useChatStream } from '../hooks/useChatStream';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { Activity, ShieldCheck, BarChart3, Headphones, ChevronRight } from 'lucide-react';

interface ChatWindowProps {
  userId: string;
  sessionId: string;
}

const SUGGESTIONS = [
  { icon: Activity, label: 'Check system health status', prompt: 'Check system health status', theme: 'green' },
  { icon: ShieldCheck, label: 'Request access for a team', prompt: 'Request access for a team', theme: 'blue' },
  { icon: BarChart3, label: 'Show system performance', prompt: 'Show system performance', theme: 'yellow' },
  { icon: Headphones, label: 'Help with IT operations', prompt: 'Help with IT operations', theme: 'pink' },
];

export const ChatWindow: React.FC<ChatWindowProps> = ({ userId, sessionId }) => {
  const { messages, status, sendMessage } = useChatStream(userId, sessionId);
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on every change
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, status.stageLabel]);

  const handleSuggestionClick = (prompt: string) => {
    if (!status.active) {
      sendMessage(prompt);
    }
  };

  return (
    <div className="chat-container">
      <div className="message-list" ref={listRef}>
        {messages.length === 0 && (
          <div className="welcome-empty-state">
            <div className="welcome-logo-container">
              <img src="/logo.png" alt="ZuuSwarm Logo" className="welcome-logo" />
            </div>
            
            <div className="welcome-text-center">
              <h2 className="welcome-title-new">
                <span className="welcome-title-gradient">ZuuSwarm</span> Operations
              </h2>
              <p className="welcome-subtitle-new">
                Ask about system health, access requests, or IT operations.<br />
                The agent routes your query across our internal APIs,<br />
                knowledge base, and operational tools.
              </p>
            </div>

            <div className="suggestion-cards-grid">
              {SUGGESTIONS.map((s, i) => {
                const Icon = s.icon;
                return (
                  <button
                    key={i}
                    className="suggestion-card-modern"
                    onClick={() => handleSuggestionClick(s.prompt)}
                    disabled={status.active}
                    type="button"
                  >
                    <div className={`suggestion-icon-container theme-${s.theme}`}>
                      <Icon size={18} className={`icon-${s.theme}`} />
                    </div>
                    <div className="suggestion-label-modern">
                      {s.label}
                    </div>
                    <ChevronRight className="suggestion-chevron" size={18} />
                  </button>
                );
              })}
            </div>
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

      {/* Disclaimer */}
      <div className="chat-disclaimer">
        ZuuSwarm AI can make mistakes. Please verify important information.
      </div>
    </div>
  );
};
