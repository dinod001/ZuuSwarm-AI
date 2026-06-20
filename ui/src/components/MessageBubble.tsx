import React from 'react';
import type { Message } from '../hooks/useChatStream';

export const MessageBubble: React.FC<{ message: Message }> = ({ message }) => {
  return (
    <div className={`message-bubble ${message.role}`}>
      {/* If we had a markdown parser like ReactMarkdown, we'd use it here. For now, we render text safely handling line breaks */}
      {message.content.split('\n').map((line, i) => (
        <span key={i}>
          {line}
          <br />
        </span>
      ))}
    </div>
  );
};
