import React, { useEffect, useState } from 'react';
import { Plus, MessageSquare, LogOut, Trash2 } from 'lucide-react';

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
      const res = await fetch(`/api/v1/chat_sessions?user_id=${userId}`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch (e) {
      // Non-critical: session list fetch failed
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 10000);
    return () => clearInterval(interval);
  }, [userId]);

  const deleteSession = async (e: React.MouseEvent, sessionIdToDelete: string) => {
    e.stopPropagation();
    try {
      const res = await fetch(`/api/v1/chat_sessions/${sessionIdToDelete}`, {
        method: "DELETE"
      });
      if (res.ok) {
        if (sessionIdToDelete === currentSessionId) {
          onNewChat();
        }
        fetchSessions();
      } else {
        console.error("Delete failed with status:", res.status);
        alert(`Delete failed: ${res.status}`);
      }
    } catch (err) {
      console.error("Delete error:", err);
      alert(`Delete error: ${err}`);
    }
  };

  return (
    <div className="sidebar-modern">
      <div className="sidebar-modern-header">
        <button className="new-chat-btn-modern" onClick={onNewChat}>
          <Plus size={14} /> New Chat
        </button>
      </div>

      <div className="sidebar-modern-content">
        <div className="sidebar-list-header">
          <div className="sidebar-list-title">
            <MessageSquare size={11} className="sidebar-icon-brand" />
            <span>CHAT</span>
            <span className="sidebar-list-count">({sessions.length})</span>
          </div>
        </div>

        <div className="sidebar-modern-list">
          {loading ? (
            <div className="sidebar-empty">Loading...</div>
          ) : sessions.length === 0 ? (
            <div className="sidebar-empty">No chat sessions yet.</div>
          ) : (
            sessions.map((session) => (
              <div
                key={session.session_id}
                className={`sidebar-item-modern ${session.session_id === currentSessionId ? 'active' : ''}`}
                onClick={() => onSelectSession(session.session_id)}
              >
                <MessageSquare size={13} className={`shrink-0 ${session.session_id === currentSessionId ? 'text-brand-400' : 'text-slate-500'}`} />
                <div className="sidebar-item-text-modern">
                  <div className="session-title-modern" title={session.title}>
                    {session.title || 'Conversation'}
                  </div>
                  <div className="session-id-modern">
                    {session.session_id}
                  </div>
                </div>
                <button
                  className="sidebar-delete-btn-modern"
                  onClick={(e) => deleteSession(e, session.session_id)}
                  title="Delete session"
                  type="button"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="sidebar-modern-footer">
        <button className="logout-btn-modern" onClick={onLogout}>
          <LogOut size={14} /> Logout
        </button>
      </div>
    </div>
  );
};

