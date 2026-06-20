import React, { useState } from 'react';

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, disabled }) => {
  const [text, setText] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim() && !disabled) {
      onSend(text);
      setText('');
    }
  };

  return (
    <div className="input-area">
      <form className="input-glass" onSubmit={handleSubmit}>
        <input
          type="text"
          className="chat-input"
          placeholder={disabled ? "Agent is thinking..." : "Ask ZuuSwarm AI..."}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          autoFocus
        />
        <button type="submit" className="send-btn" disabled={!text.trim() || disabled}>
          <svg className="send-icon" viewBox="0 0 24 24">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
      </form>
    </div>
  );
};
