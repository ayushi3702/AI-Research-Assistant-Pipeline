import { useState, useEffect, useRef } from "react";

export default function Navbar({ user, onLogout, onGoogleLogin, apiBase, token, canShare, shareUrl, shareCopied, onShare, onRevokeShare, onCopyShareUrl }) {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const [showLogin, setShowLogin] = useState(false);
  const [showNotifs, setShowNotifs] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const notifRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  // Fetch notifications on mount and every 30s
  useEffect(() => {
    if (!user || !token) return;
    const fetchNotifs = async () => {
      try {
        const res = await fetch(`${apiBase}/notifications`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setNotifications(data.notifications || []);
          setUnreadCount(data.unread_count || 0);
        }
      } catch {}
    };
    fetchNotifs();
    const interval = setInterval(fetchNotifs, 30000);
    return () => clearInterval(interval);
  }, [user, token, apiBase]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setShowNotifs(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const toggleTheme = () => setTheme((t) => (t === "light" ? "dark" : "light"));

  const markAllRead = async () => {
    try {
      await fetch(`${apiBase}/notifications/read-all`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {}
  };

  const markRead = async (id) => {
    try {
      await fetch(`${apiBase}/notifications/${id}/read`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}` },
      });
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {}
  };

  const timeAgo = (dateStr) => {
    if (!dateStr) return "";
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  };

  return (
    <>
      <nav className="navbar">
        <div className="navbar-brand">🔬 AI Research Assistant</div>
        <div className="navbar-actions">
          <button className="theme-toggle" onClick={toggleTheme} title="Toggle theme">
            {theme === "light" ? "🌙" : "☀️"}
          </button>
          {user && (
            <div className="notif-container" ref={notifRef}>
              <button
                className="notif-bell"
                onClick={() => setShowNotifs(!showNotifs)}
                title="Notifications"
              >
                🔔
                {unreadCount > 0 && <span className="notif-badge">{unreadCount}</span>}
              </button>
              {showNotifs && (
                <div className="notif-dropdown">
                  <div className="notif-dropdown-header">
                    <span className="notif-dropdown-title">Notifications</span>
                    {unreadCount > 0 && (
                      <button className="notif-mark-all" onClick={markAllRead}>
                        Mark all read
                      </button>
                    )}
                  </div>
                  <div className="notif-dropdown-list">
                    {notifications.length === 0 ? (
                      <div className="notif-empty">No notifications yet</div>
                    ) : (
                      notifications.map((n) => (
                        <div
                          key={n.id}
                          className={`notif-item${n.is_read ? "" : " unread"}`}
                          onClick={() => { if (!n.is_read) markRead(n.id); }}
                        >
                          <div className="notif-item-icon">
                            {n.type === "report_ready" ? "📄" : "📬"}
                          </div>
                          <div className="notif-item-content">
                            <div className="notif-item-subject">{n.subject}</div>
                            <div className="notif-item-preview">{n.preview}</div>
                            <div className="notif-item-meta">
                              <span className="notif-item-time">{timeAgo(n.created_at)}</span>
                              <span className={`notif-item-status ${n.status}`}>
                                {n.status === "sent" ? "✓ Sent" : "✗ Failed"}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
          {user && canShare && (
            <div className="navbar-share">
              {shareUrl ? (
                <div className="share-active">
                  <button className="btn-share" onClick={onCopyShareUrl}>
                    {shareCopied ? "✅ Copied!" : "🔗 Share"}
                  </button>
                  <button className="btn-share-revoke" onClick={onRevokeShare} title="Revoke share link">✕</button>
                </div>
              ) : (
                <button className="btn-share" onClick={onShare}>
                  🔗 Share
                </button>
              )}
            </div>
          )}
          {user ? (
            <div className="navbar-user">
              <span className="navbar-user-name">{user.name || user.email}</span>
              <button className="btn-ghost" onClick={onLogout}>Logout</button>
            </div>
          ) : (
            <button className="btn-primary" onClick={() => setShowLogin(true)}>
              Sign in
            </button>
          )}
        </div>
      </nav>

      {showLogin && (
        <div className="modal-overlay" onClick={() => setShowLogin(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Sign in</h2>
            <p className="login-subtitle">Continue with your Google account</p>

            <button
              className="btn-google"
              onClick={() => { setShowLogin(false); onGoogleLogin(); }}
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
                <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
                <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
                <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.581-2.581C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
              </svg>
              Continue with Google
            </button>

            <p className="login-note">
              New users are automatically registered on first sign-in.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
