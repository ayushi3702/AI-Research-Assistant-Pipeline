/**
 * TrustHeatmap — renders the research report with inline fact-check highlighting.
 *
 * Claims are color-coded by verification status (verified / disputed /
 * unverified) and expose a tooltip with supporting/contradicting sources, plus
 * an overall confidence summary bar.
 */
import { useState, useMemo } from "react";
import ReactMarkdown from "react-markdown";

const STATUS_CONFIG = {
  verified: { color: "rgba(34, 197, 94, 0.15)", border: "#22c55e", icon: "✓", label: "Verified" },
  disputed: { color: "rgba(239, 68, 68, 0.15)", border: "#ef4444", icon: "✗", label: "Contradicted" },
  unverified: { color: "rgba(245, 158, 11, 0.15)", border: "#f59e0b", icon: "⚠", label: "Uncertain" },
};

function ClaimTooltip({ claim, onClose }) {
  const config = STATUS_CONFIG[claim.status] || STATUS_CONFIG.unverified;

  return (
    <div className="claim-tooltip" onClick={(e) => e.stopPropagation()}>
      <div className="claim-tooltip-header">
        <span className="claim-tooltip-icon" style={{ color: config.border }}>{config.icon}</span>
        <span className="claim-tooltip-status" style={{ color: config.border }}>{config.label}</span>
        <span className="claim-tooltip-confidence">
          {Math.round((claim.confidence || 0) * 100)}% confidence
        </span>
      </div>
      <div className="claim-tooltip-claim">{claim.claim}</div>
      {claim.supported_by && claim.supported_by.length > 0 && (
        <div className="claim-tooltip-sources">
          <span className="claim-tooltip-sources-label">Supported by:</span>
          {claim.supported_by.map((url, i) => (
            <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="claim-source-link">
              {(() => { try { return new URL(url).hostname; } catch { return url; } })()}
            </a>
          ))}
        </div>
      )}
      {claim.contradicted_by && claim.contradicted_by.length > 0 && (
        <div className="claim-tooltip-sources contradicted">
          <span className="claim-tooltip-sources-label">Contradicted by:</span>
          {claim.contradicted_by.map((url, i) => (
            <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="claim-source-link contradicted">
              {(() => { try { return new URL(url).hostname; } catch { return url; } })()}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function ConfidenceBar({ claims }) {
  if (!claims || claims.length === 0) return null;

  const verified = claims.filter(c => c.status === "verified").length;
  const disputed = claims.filter(c => c.status === "disputed").length;
  const unverified = claims.filter(c => c.status === "unverified").length;
  const total = claims.length;
  const avgConfidence = claims.reduce((sum, c) => sum + (c.confidence || 0), 0) / total;

  return (
    <div className="confidence-bar-container">
      <div className="confidence-bar-header">
        <span className="confidence-bar-title">🛡️ Fact-Check Summary</span>
        <span className="confidence-bar-score">
          {Math.round(avgConfidence * 100)}% avg confidence
        </span>
      </div>
      <div className="confidence-bar">
        {verified > 0 && (
          <div
            className="confidence-segment verified"
            style={{ width: `${(verified / total) * 100}%` }}
            title={`${verified} verified claims`}
          />
        )}
        {unverified > 0 && (
          <div
            className="confidence-segment unverified"
            style={{ width: `${(unverified / total) * 100}%` }}
            title={`${unverified} uncertain claims`}
          />
        )}
        {disputed > 0 && (
          <div
            className="confidence-segment disputed"
            style={{ width: `${(disputed / total) * 100}%` }}
            title={`${disputed} contradicted claims`}
          />
        )}
      </div>
      <div className="confidence-bar-legend">
        <span className="legend-item verified">✓ {verified} verified</span>
        <span className="legend-item unverified">⚠ {unverified} uncertain</span>
        <span className="legend-item disputed">✗ {disputed} contradicted</span>
      </div>
    </div>
  );
}

export default function TrustHeatmap({ report, claims, loading }) {
  const [activeClaim, setActiveClaim] = useState(null);
  const [heatmapEnabled, setHeatmapEnabled] = useState(true);

  // Map claims to report paragraphs using word overlap
  const paragraphClaims = useMemo(() => {
    if (!claims || claims.length === 0 || !report) return {};

    // Split report into paragraphs (by double newline or markdown blocks)
    const paragraphs = report.split(/\n\n+/).map(p =>
      p.replace(/#{1,6}\s/g, "").replace(/\*\*/g, "").replace(/\*/g, "").replace(/\[(\d+)\]/g, "").trim()
    ).filter(p => p.length > 20);

    const mapping = {};

    claims.forEach(claim => {
      const claimWords = new Set(
        claim.claim.toLowerCase().replace(/[^\w\s]/g, "").split(/\s+/).filter(w => w.length > 3)
      );

      let bestIdx = -1;
      let bestScore = 0;

      paragraphs.forEach((para, idx) => {
        const paraWords = new Set(
          para.toLowerCase().replace(/[^\w\s]/g, "").split(/\s+/).filter(w => w.length > 3)
        );
        const overlap = [...claimWords].filter(w => paraWords.has(w)).length;
        const score = overlap / Math.max(claimWords.size, 1);
        if (score > bestScore && score > 0.35) {
          bestScore = score;
          bestIdx = idx;
        }
      });

      if (bestIdx >= 0) {
        const key = paragraphs[bestIdx].substring(0, 80).toLowerCase();
        if (!mapping[key] || bestScore > (mapping[key]._score || 0)) {
          mapping[key] = { ...claim, _score: bestScore };
        }
      }
    });

    return mapping;
  }, [report, claims]);

  // Find matching claim for a block of text
  const findClaimForText = (text) => {
    if (!text || !heatmapEnabled) return null;
    const cleanText = text.toLowerCase().replace(/[^\w\s]/g, "").trim();
    if (cleanText.length < 20) return null;

    for (const [key, claim] of Object.entries(paragraphClaims)) {
      const keyWords = new Set(key.replace(/[^\w\s]/g, "").split(/\s+/).filter(w => w.length > 3));
      const textWords = new Set(cleanText.split(/\s+/).filter(w => w.length > 3));
      const overlap = [...keyWords].filter(w => textWords.has(w)).length;
      if (overlap >= 3 && overlap / keyWords.size > 0.4) {
        return claim;
      }
    }
    return null;
  };

  const getTextFromChildren = (children) => {
    if (typeof children === "string") return children;
    if (Array.isArray(children)) return children.map(c =>
      typeof c === "string" ? c : c?.props?.children ? getTextFromChildren(c.props.children) : ""
    ).join("");
    if (children?.props?.children) return getTextFromChildren(children.props.children);
    return "";
  };

  // Custom renderer for ReactMarkdown that highlights matched content
  const components = useMemo(() => {
    if (!heatmapEnabled || !claims || claims.length === 0) return {};

    const wrapWithHighlight = (children, textContent) => {
      const claim = findClaimForText(textContent);
      if (!claim) return null;
      const config = STATUS_CONFIG[claim.status] || STATUS_CONFIG.unverified;
      return (
        <div
          className={`heatmap-sentence status-${claim.status}`}
          style={{
            background: config.color,
            borderLeft: `3px solid ${config.border}`,
            paddingLeft: "12px",
            borderRadius: "4px",
            position: "relative",
            cursor: "pointer",
            margin: "0.5em 0",
          }}
          onClick={(e) => { e.stopPropagation(); setActiveClaim(activeClaim?.id === claim.id ? null : claim); }}
        >
          <span className="heatmap-indicator" style={{ color: config.border }}>
            {config.icon}
          </span>
          {children}
          {activeClaim?.id === claim.id && <ClaimTooltip claim={claim} onClose={() => setActiveClaim(null)} />}
        </div>
      );
    };

    return {
      p: ({ children, ...props }) => {
        const text = getTextFromChildren(children);
        const highlighted = wrapWithHighlight(<p {...props}>{children}</p>, text);
        if (highlighted) return highlighted;
        return <p {...props}>{children}</p>;
      },
      blockquote: ({ children, ...props }) => {
        const text = getTextFromChildren(children);
        const highlighted = wrapWithHighlight(<blockquote {...props}>{children}</blockquote>, text);
        if (highlighted) return highlighted;
        return <blockquote {...props}>{children}</blockquote>;
      },
      li: ({ children, ...props }) => {
        const text = getTextFromChildren(children);
        const highlighted = wrapWithHighlight(<li {...props}>{children}</li>, text);
        if (highlighted) return highlighted;
        return <li {...props}>{children}</li>;
      },
    };
  }, [heatmapEnabled, claims, paragraphClaims, activeClaim]);

  if (loading) {
    return (
      <div className="trust-heatmap-loading">
        <span className="heatmap-loading-icon">🔍</span>
        <span>Verifying claims...</span>
      </div>
    );
  }

  return (
    <div className="trust-heatmap">
      <ConfidenceBar claims={claims} />

      <div className="heatmap-toggle">
        <label className="heatmap-toggle-label">
          <input
            type="checkbox"
            checked={heatmapEnabled}
            onChange={(e) => setHeatmapEnabled(e.target.checked)}
          />
          <span className="heatmap-toggle-text">Show trust heatmap</span>
        </label>
        {heatmapEnabled && claims?.length > 0 && (
          <span className="heatmap-hint">Click highlighted text to see details</span>
        )}
      </div>

      <div className="heatmap-report-content" onClick={() => setActiveClaim(null)}>
        <ReactMarkdown components={components}>{report}</ReactMarkdown>
      </div>
    </div>
  );
}
