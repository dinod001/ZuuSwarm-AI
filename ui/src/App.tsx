import React, { useState } from 'react';
import { ChatWindow } from './components/ChatWindow';
import { LoginScreen } from './components/LoginScreen';
import { Sidebar } from './components/Sidebar';
import { VoiceRoom } from './components/VoiceRoom';
import { Phone, X } from 'lucide-react';
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
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [autoStartVoice, setAutoStartVoice] = useState(false);

  React.useEffect(() => {
    const handleOpenVoice = (e: any) => {
      setVoiceOpen(true);
      setAutoStartVoice(!!e.detail?.autoStart);
    };
    window.addEventListener('zuuswarm:open_voice', handleOpenVoice);
    return () => window.removeEventListener('zuuswarm:open_voice', handleOpenVoice);
  }, []);

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

  const handleLogout = () => {
    setUserInfo(null);
    setSessionId(null);
  };

  const handleNewChat = () => {
    setSessionId(crypto.randomUUID());
  };

  const handleSelectSession = (sid: string) => {
    setSessionId(sid);
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
      <div className="ambient-orb-1"></div>
      <div className="ambient-orb-2"></div>
      
      <main style={{ flex: 1, display: 'flex', overflow: 'hidden', padding: '1.5rem', gap: '1.5rem', zIndex: 10 }}>
        <Sidebar 
          userId={userInfo.user_id}
          currentSessionId={sessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onLogout={handleLogout}
        />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: '24px', backdropFilter: 'blur(24px)', boxShadow: 'var(--glass-shadow)', overflow: 'hidden' }}>
          <header className="header" style={{ margin: '0', borderRadius: '0', borderBottom: '1px solid var(--glass-border)', borderTop: 'none', borderLeft: 'none', borderRight: 'none', boxShadow: 'none' }}>
            <img src="/logo.png" alt="ZuuSwarm AI Logo" className="logo" />
            <span className="header-title">ZuuSwarm Operations</span>
            
            <button
              onClick={() => setVoiceOpen(true)}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px', 
                padding: '8px 16px', borderRadius: '20px', 
                background: 'rgba(16, 185, 129, 0.15)', 
                border: '1px solid rgba(16, 185, 129, 0.4)',
                color: '#6ee7b7', cursor: 'pointer',
                marginLeft: '16px', fontWeight: 500, fontSize: '0.85rem'
              }}
              title="Talk to the assistant"
            >
              <Phone size={16} />
              Voice
            </button>

            <div style={{ marginLeft: 'auto', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Logged in as: <strong style={{ color: 'var(--text-primary)' }}>{userInfo.name}</strong>
            </div>
          </header>
          <ChatWindow userId={userInfo.user_id} sessionId={sessionId} key={sessionId} />
        </div>
      </main>

      {/* Voice modal */}
      {voiceOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999,
          background: 'rgba(2, 6, 23, 0.85)', backdropFilter: 'blur(12px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <button
            onClick={() => setVoiceOpen(false)}
            style={{
              position: 'absolute', top: '16px', right: '16px',
              padding: '8px', borderRadius: '50%', background: '#1e293b',
              color: '#e2e8f0', cursor: 'pointer', border: 'none'
            }}
            title="Close"
          >
            <X size={18} />
          </button>
          <VoiceRoom
            userId={userInfo.user_id}
            sessionId={sessionId}
            onClose={() => setVoiceOpen(false)}
            autoStart={autoStartVoice}
          />
        </div>
      )}
    </div>
  );
}

export default App;
