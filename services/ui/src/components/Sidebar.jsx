/**
 * Sidebar — collapsible panel listing the user's chat/research history.
 *
 * Loads recent chats for the authenticated user, supports pinning and
 * selecting a chat, and starting a new conversation.
 */
import { useState, useEffect } from "react";

/** Derive up-to-two-letter initials from a user's name or email for the avatar. */
function getInitials(user) {
  if (!user) return "";
  if (user.name) {
    return user.name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  }
  return user.email ? user.email[0].toUpperCase() : "";
}

export default function Sidebar({ apiBase, onSelectChat, onNewChat, token, user, authLoading }) {
  const [chats, setChats] = useState([]);
  const [error, setError] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [loadingChats, setLoadingChats] = useState(!!token);

  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const refreshChats = () => {
    if (!token) return;
    fetch(`${apiBase}/chats`, { headers })
      .then((res) => res.json())
      .then((data) => setChats(Array.isArray(data) ? data.slice(0, 30) : []))
      .catch(() => setError(true))
      .finally(() => setLoadingChats(false));
  };

  const togglePin = (e, chatId) => {
    e.stopPropagation();
    fetch(`${apiBase}/chats/${chatId}/pin`, { method: "PATCH", headers })
      .then((res) => { if (res.ok) refreshChats(); });
  };

  useEffect(() => {
    if (!token) {
      setChats([]);
      setError(false);
      setLoadingChats(false);
      return;
    }
    setLoadingChats(true);
    refreshChats();
    const interval = setInterval(refreshChats, 15000);
    return () => clearInterval(interval);
  }, [apiBase, token]);

  const groupByDate = (items) => {
    const today = new Date().toDateString();
    const yesterday = new Date(Date.now() - 86400000).toDateString();

    const groups = { Pinned: [], Today: [], Yesterday: [], Earlier: [] };

    items.forEach((item) => {
      if (item.pinned) {
        groups.Pinned.push(item);
        return;
      }
      const date = new Date(item.created_at).toDateString();
      if (date === today) groups.Today.push(item);
      else if (date === yesterday) groups.Yesterday.push(item);
      else groups.Earlier.push(item);
    });

    return groups;
  };

  const groups = groupByDate(chats);

  const ToggleIcon = () => (
    <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1" y="2" width="14" height="12" rx="2" />
      <line x1="5.5" y1="2" x2="5.5" y2="14" />
    </svg>
  );

  return (
    <div className="sidebar-container">
      {/* Expanded sidebar */}
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <div className="sidebar-header">
          <h2>Chat History</h2>
          <button
            className="sidebar-toggle"
            onClick={() => setCollapsed(true)}
            title="Close sidebar"
          >
            <ToggleIcon />
          </button>
        </div>

        {token && (
          <button className="sidebar-new-chat" onClick={() => onNewChat && onNewChat()}>
            <span className="new-chat-icon">✏️</span> New Chat
          </button>
        )}

        {!token && authLoading && (
          <div className="sidebar-loading">
            <span className="content-spinner" />
            <span>Loading chats…</span>
          </div>
        )}

        {!token && !authLoading && (
          <p className="sidebar-empty">Login to see chat history</p>
        )}

        {token && (loadingChats || authLoading) && chats.length === 0 && !error && (
          <div className="sidebar-loading">
            <span className="content-spinner" />
            <span>Loading chats…</span>
          </div>
        )}

        {token && !error && !loadingChats && !authLoading && chats.length === 0 && (
          <p className="sidebar-empty">No chat history yet</p>
        )}

        {token && Object.entries(groups).map(([label, items]) =>
          items.length > 0 ? (
            <div key={label} className="sidebar-group">
              <p className="sidebar-group-label">{label === "Pinned" ? "📌 Pinned" : label}</p>
              {items.map((chat) => (
                <div
                  key={chat.id}
                  className="sidebar-job"
                  onClick={() => onSelectChat && onSelectChat(chat)}
                >
                  <span className="sidebar-job-query">{chat.title}</span>
                  <div className="sidebar-job-actions">
                    <button
                      className={`sidebar-pin-btn${chat.pinned ? " pinned" : ""}`}
                      onClick={(e) => togglePin(e, chat.id)}
                      title={chat.pinned ? "Unpin" : "Pin"}
                    >
                      📌
                    </button>
                    <span className={`sidebar-chat-type type-${chat.type.toLowerCase().replace(/[^a-z]/g, "")}`}>
                      {chat.type === "Research" ? "📄" : "💬"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : null
        )}
      </aside>

      {/* Collapsed thin rail */}
      {collapsed && (
        <div className="sidebar-rail">
          <button
            className="sidebar-toggle"
            onClick={() => setCollapsed(false)}
            title="Open sidebar"
          >
            <ToggleIcon />
          </button>
          {token && (
            <button
              className="sidebar-rail-new-chat"
              onClick={() => onNewChat && onNewChat()}
              title="New Chat"
            >
              ✏️
            </button>
          )}
          <div className="sidebar-rail-spacer" />
          {user && (
            <div className="sidebar-rail-avatar" title={user.name || user.email}>
              {getInitials(user)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
