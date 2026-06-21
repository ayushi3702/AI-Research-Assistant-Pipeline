/**
 * AgentCard — compact status tile for a single pipeline agent.
 *
 * @param {string} icon   Emoji/icon representing the agent.
 * @param {string} label  Human-readable agent name.
 * @param {string} status One of waiting | running | done | failed | skipped.
 */
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
