export default function AgentCard({ icon, label, status }) {
  const statusIcons = {
    waiting: "⬜",
    running: "🔄",
    done: "✅",
    failed: "❌",
    skipped: "⏭️",
  };

  return (
    <div className={`agent-card ${status}`}>
      <div className="agent-icon">{icon}</div>
      <div className="agent-label">{label}</div>
      <div className="agent-status">
        {statusIcons[status] || "⬜"} {status.charAt(0).toUpperCase() + status.slice(1)}
      </div>
    </div>
  );
}
