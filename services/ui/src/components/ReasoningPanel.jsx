import { useState, useEffect, useRef } from "react";

/**
 * ReasoningPanel — Live agent reasoning trace display.
 * Shows a timeline of agent thought processes, decisions, and reasoning steps.
 * Streams live during pipeline execution, loads from DB for completed jobs.
 */

const AGENT_CONFIG = {
  search: { icon: "🔍", label: "Search Agent", color: "#3b82f6" },
  extractor: { icon: "📄", label: "Extractor Agent", color: "#8b5cf6" },
  validator: { icon: "✅", label: "Validator Agent", color: "#22c55e" },
  rag: { icon: "🧠", label: "RAG Agent", color: "#f59e0b" },
  writer: { icon: "✍️", label: "Writer Agent", color: "#ec4899" },
};

function TraceEntry({ trace, isLatest }) {
  const config = AGENT_CONFIG[trace.agent] || { icon: "⚙️", label: trace.agent, color: "#6b7280" };

  return (
    <div className={`trace-entry${isLatest ? " trace-latest" : ""}`}>
      <div className="trace-timeline">
        <div className="trace-dot" style={{ background: config.color }} />
        <div className="trace-line" />
      </div>
      <div className="trace-content">
        <div className="trace-header">
          <span className="trace-agent-badge" style={{ background: `${config.color}15`, color: config.color, borderColor: `${config.color}40` }}>
            <span className="trace-agent-icon">{config.icon}</span>
            {config.label}
          </span>
          <span className="trace-step-badge">{trace.step.replace(/_/g, " ")}</span>
        </div>
        <div className="trace-reasoning">
          <span className="trace-thought-icon">💭</span>
          {trace.reasoning}
        </div>
        {trace.decision && (
          <div className="trace-decision">
            <span className="trace-decision-icon">→</span>
            <span className="trace-decision-text">{trace.decision}</span>
          </div>
        )}
        {trace.metadata && Object.keys(trace.metadata).length > 0 && (
          <div className="trace-metadata">
            {Object.entries(trace.metadata).map(([key, value]) => (
              <span key={key} className="trace-meta-chip">
                {key}: <strong>{typeof value === 'number' ? value : String(value)}</strong>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ReasoningPanel({ traces, isLive, expanded, onToggle }) {
  const scrollRef = useRef(null);

  // Auto-scroll to bottom when new traces arrive during live mode
  useEffect(() => {
    if (isLive && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [traces, isLive]);

  const traceCount = traces.length;

  return (
    <div className={`reasoning-panel${expanded ? " expanded" : ""}`}>
      <button className="reasoning-panel-toggle" onClick={onToggle}>
        <span className="reasoning-toggle-icon">🧪</span>
        <span className="reasoning-toggle-label">
          Agent Reasoning Trace
          {traceCount > 0 && <span className="reasoning-count">{traceCount}</span>}
        </span>
        {isLive && <span className="reasoning-live-badge">● LIVE</span>}
        <span className={`reasoning-chevron${expanded ? " open" : ""}`}>▸</span>
      </button>

      {expanded && (
        <div className="reasoning-panel-body" ref={scrollRef}>
          {traces.length === 0 ? (
            <div className="reasoning-empty">
              {isLive ? (
                <>
                  <span className="reasoning-empty-icon">⏳</span>
                  <span>Waiting for agents to start reasoning...</span>
                </>
              ) : (
                <>
                  <span className="reasoning-empty-icon">📝</span>
                  <span>No reasoning traces available for this job</span>
                </>
              )}
            </div>
          ) : (
            <div className="reasoning-timeline">
              {traces.map((trace, i) => (
                <TraceEntry
                  key={trace.id || i}
                  trace={trace}
                  isLatest={i === traces.length - 1 && isLive}
                />
              ))}
              {isLive && (
                <div className="trace-entry trace-thinking">
                  <div className="trace-timeline">
                    <div className="trace-dot thinking" />
                  </div>
                  <div className="trace-content">
                    <span className="trace-thinking-dots">
                      <span>●</span><span>●</span><span>●</span>
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
