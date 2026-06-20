import React, { useState } from 'react';
import logoUrl from './assets/logo.png';
import { ChatWindow } from './components/ChatWindow';
import { LoginScreen } from './components/LoginScreen';
import './App.css';

interface UserInfo {
  user_id: string;
  name: string;
  email: string;
}

function App() {
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  const handleLogin = async (email: string) => {
    setIsLoggingIn(true);
    setLoginError(null);
    try {
      const res = await fetch('http://localhost:8000/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      if (!res.ok) {
        throw new Error('Employee not found or inactive');
      }
      const data = await res.json();
      setUserInfo(data);
      const newSessionId = crypto.randomUUID();
      setSessionId(newSessionId);
      
      // Optional: pre-warm the session
      fetch('http://localhost:8000/api/v1/sessions/warmup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: data.user_id, session_id: newSessionId })
      }).catch(console.error);
      
    } catch (e: any) {
      setLoginError(e.message);
    } finally {
      setIsLoggingIn(false);
    }
  };

  if (!userInfo || !sessionId) {
    return (
      <div style={{position: 'relative', width: '100%', height: '100%'}}>
        <LoginScreen onLogin={handleLogin} />
        {isLoggingIn && <div style={{position: 'absolute', top: '20px', left: '50%', transform: 'translateX(-50%)', color: 'rgba(255,255,255,0.7)'}}>Authenticating...</div>}
        {loginError && <div style={{position: 'absolute', top: '50px', left: '50%', transform: 'translateX(-50%)', color: 'var(--accent-red)', background: 'rgba(20,20,20,0.8)', padding: '0.5rem 1rem', borderRadius: '4px'}}>{loginError}</div>}
      </div>
    );
  }

  return (
    <div className="app-container">
      <header className="header">
        <img src={logoUrl} alt="ZuuSwarm AI Logo" className="logo" />
        <span className="header-title">ZuuSwarm Operations</span>
        <div style={{ marginLeft: 'auto', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          Logged in as: <strong>{userInfo.name} ({userInfo.user_id})</strong>
        </div>
      </header>
      
      <main style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <ChatWindow userId={userInfo.user_id} sessionId={sessionId} />
      </main>
    </div>
  );
}

export default App;
