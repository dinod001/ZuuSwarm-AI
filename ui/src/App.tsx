import React, { useState, useEffect } from 'react';
import { ChatWindow } from './components/ChatWindow';
import { LoginScreen } from './components/LoginScreen';
import { LandingPage } from './components/LandingPage';
import { Sidebar } from './components/Sidebar';
import { VoiceRoom } from './components/VoiceRoom';
import { Mic, X, Settings, Bell, HelpCircle, Clock, ChevronDown } from 'lucide-react';
import './App.css';

interface UserInfo {
  user_id: string;
  name: string;
  email: string;
}

type AppView = 'landing' | 'login' | 'chat';

function App() {
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [autoStartVoice, setAutoStartVoice] = useState(false);
  const [view, setView] = useState<AppView>('landing');
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

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
      const res = await fetch('/api/v1/auth/login', {
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
      setView('chat');
      
      // Optional: pre-warm the session
      fetch('/api/v1/sessions/warmup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: data.user_id, session_id: newSessionId })
      }).catch(() => { /* non-critical */ });
      
    } catch (e: any) {
      setLoginError(e.message);
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = () => {
    setUserInfo(null);
    setSessionId(null);
    setView('landing');
  };

  const handleNewChat = () => {
    setSessionId(crypto.randomUUID());
  };

  const handleSelectSession = (sid: string) => {
    setSessionId(sid);
  };

  // ── LANDING PAGE ──
  if (view === 'landing') {
    return <LandingPage onGoToLogin={() => setView('login')} />;
  }

  // ── LOGIN SCREEN ──
  if (view === 'login' && (!userInfo || !sessionId)) {
    return (
      <div style={{position: 'relative', width: '100%', height: '100%'}}>
        <div className="ambient-orb-1" />
        <div className="ambient-orb-2" />
        <LoginScreen onLogin={handleLogin} onBack={() => setView('landing')} />
        {isLoggingIn && (
          <div style={{
            position: 'absolute', top: '20px', left: '50%',
            transform: 'translateX(-50%)',
            color: 'rgba(255,255,255,0.7)',
            zIndex: 20
          }}>
            Authenticating...
          </div>
        )}
        {loginError && (
          <div style={{
            position: 'absolute', top: '50px', left: '50%',
            transform: 'translateX(-50%)',
            color: '#f87171',
            background: 'rgba(20,15,40,0.9)',
            padding: '0.5rem 1rem',
            borderRadius: '8px',
            border: '1px solid rgba(248,113,113,0.2)',
            zIndex: 20
          }}>
            {loginError}
          </div>
        )}
      </div>
    );
  }

  // ── MAIN CHAT APPLICATION ──
  if (!userInfo || !sessionId) {
    // Safety fallback — redirect to landing
    return <LandingPage onGoToLogin={() => setView('login')} />;
  }

  return (
    <div className="app-container">
      <div className="ambient-orb-1" />
      <div className="ambient-orb-2" />
      
      <main style={{ flex: 1, display: 'flex', overflow: 'hidden', padding: 'clamp(0.5rem, 1.5vh, 1rem)', gap: 'clamp(0.5rem, 1.5vh, 1rem)', zIndex: 10, minHeight: 0 }}>
        <Sidebar 
          userId={userInfo.user_id}
          currentSessionId={sessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onLogout={handleLogout}
        />
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          background: 'var(--glass-bg)',
          border: '1px solid var(--glass-border)',
          borderRadius: '24px',
          backdropFilter: 'blur(24px)',
          boxShadow: 'var(--glass-shadow)',
          overflow: 'hidden',
          position: 'relative',
          minHeight: 0
        }}>
          {/* Elegant soft animated background for the chat area */}
          <div className="chat-elegant-bg" />
          
          <header className="header" style={{
            margin: '0', borderRadius: '0',
            borderBottom: '1px solid var(--glass-border)',
            borderTop: 'none', borderLeft: 'none', borderRight: 'none',
            boxShadow: 'none',
            background: 'rgba(12, 16, 41, 0.4)',
            backdropFilter: 'blur(12px)',
            position: 'relative',
            zIndex: 10,
            padding: 'clamp(0.5rem, 1.5vh, 1rem) clamp(1rem, 2vw, 1.5rem)',
            minHeight: 'clamp(50px, 8vh, 70px)'
          }}>
            <img src="/logo.png" alt="ZuuSwarm AI Logo" className="logo" style={{ height: 'clamp(20px, 3vh, 28px)' }} />
            <span className="header-title" style={{ fontSize: 'clamp(0.9rem, 2vh, 1.05rem)', color: 'white' }}>ZuuSwarm Operations</span>
            
            <button
              className="premium-voice-btn"
              onClick={() => {
                setAutoStartVoice(false);
                setVoiceOpen(true);
              }}
              title="Talk to the assistant"
              type="button"
            >
              <div className="pulse-dot-green-small" />
              <Mic size={14} />
              Voice Connected
            </button>

            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
              {/* Realtime Clock */}
              <div className="header-clock">
                <Clock size={14} />
                <span>
                  {currentTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
                <span className="clock-date">
                  {currentTime.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}
                </span>
              </div>

              {/* Utility Icons */}
              <div className="header-utilities">
                <button className="util-btn" title="Notifications"><Bell size={18} /></button>
                <button className="util-btn" title="Help"><HelpCircle size={18} /></button>
                <button className="util-btn" title="Settings"><Settings size={18} /></button>
              </div>

              {/* User Chip */}
              <div className="user-chip">
                <div className="user-avatar">{userInfo.name.charAt(0).toUpperCase()}</div>
                <div className="user-info-text">
                  <span className="user-role">Administrator</span>
                  <span className="user-name">{userInfo.name}</span>
                </div>
                <ChevronDown size={14} className="user-chevron" />
              </div>
            </div>
          </header>
          
          <div style={{ flex: 1, position: 'relative', zIndex: 10, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <ChatWindow userId={userInfo.user_id} sessionId={sessionId} key={sessionId} />
          </div>
        </div>
      </main>

      {/* Voice modal */}
      {voiceOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999,
          background: 'rgba(6, 2, 15, 0.88)', backdropFilter: 'blur(12px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <button
            onClick={() => setVoiceOpen(false)}
            style={{
              position: 'absolute', top: '16px', right: '16px',
              padding: '8px', borderRadius: '50%', background: 'var(--bg-elevated)',
              color: '#e2e8f0', cursor: 'pointer', border: 'none'
            }}
            title="Close"
            type="button"
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
