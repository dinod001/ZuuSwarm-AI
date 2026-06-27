import React, { useState } from 'react';
import { Send, Sparkles } from 'lucide-react';

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
        <div className="input-prefix-icon">
          <Sparkles size={18} />
        </div>
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
          <Send size={18} className="send-icon" />
        </button>
      </form>
    </div>
  );
};
