import React from 'react';
import type { Message } from '../hooks/useChatStream';

export const MessageBubble: React.FC<{ message: Message }> = ({ message }) => {
  // Use a fallback time if the message doesn't have a timestamp, or just use current time for now since it's a UI mockup
  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <div className={`message-wrapper ${message.role}`}>
      <div className={`message-bubble ${message.role}`}>
        {/* If we had a markdown parser like ReactMarkdown, we'd use it here. For now, we render text safely handling line breaks */}
        {message.content.split('\n').map((line, i) => (
          <span key={i}>
            {line}
            <br />
          </span>
        ))}
      </div>
      <div className="message-time">{timeStr}</div>
    </div>
  );
};
