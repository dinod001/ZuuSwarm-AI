import React, { useState } from 'react';

interface LoginScreenProps {
  onLogin: (email: string) => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ onLogin }) => {
  const [email, setEmail] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email.trim()) {
      onLogin(email.trim());
    }
  };

  return (
    <div className="login-container">
      <div className="ambient-orb-1"></div>
      <div className="ambient-orb-2"></div>
      <div className="login-card">
        <img src="/logo.png" alt="ZuuSwarm AI Logo" className="login-logo" />
        <h2>ZuuSwarm Operations</h2>
        <p className="login-subtitle">Enter your employee email to access the IT Ops Swarm.</p>
        
        <form onSubmit={handleSubmit} className="login-form">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="e.g., ming.clark6@zuucrew.ai"
            className="login-input"
            required
            autoFocus
          />
          <button type="submit" className="login-btn" disabled={!email.trim()}>
            Login
          </button>
        </form>
      </div>
    </div>
  );
};
