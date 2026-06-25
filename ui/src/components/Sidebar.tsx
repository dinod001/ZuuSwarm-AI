import React, { useEffect, useState } from 'react';

interface ChatSessionMeta {
  session_id: string;
  employ_id: string;
  title: string;
  last_message_at: number;
}

interface SidebarProps {
  userId: string;
  currentSessionId: string;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onLogout: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  userId,
  currentSessionId,
  onSelectSession,
  onNewChat,
  onLogout,
}) => {
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchSessions = async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/chat_sessions?user_id=${userId}`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch (e) {
      console.error("Failed to load sessions", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
    // Set up an interval to refresh the session list every 10 seconds
    const interval = setInterval(fetchSessions, 10000);
    return () => clearInterval(interval);
  }, [userId]);

  return (
    <div className="sidebar">
      <button className="new-chat-btn" onClick={onNewChat}>
        + New Chat
      </button>

      <div className="sidebar-list">
        <h3 className="sidebar-heading">Recent Conversations</h3>
        {loading ? (
          <div className="sidebar-loading">Loading...</div>
        ) : sessions.length === 0 ? (
          <div className="sidebar-empty">No past conversations</div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.session_id}
              className={`sidebar-item ${session.session_id === currentSessionId ? 'active' : ''}`}
              onClick={() => onSelectSession(session.session_id)}
            >
              <span className="session-title" title={session.title}>
                {session.title || 'Conversation'}
              </span>
            </div>
          ))
        )}
      </div>

      <button className="logout-btn" onClick={onLogout}>
        Logout
      </button>
    </div>
  );
};
