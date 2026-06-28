import React from "react";
import type { AgentSnapshot } from "../lib/agentTypes";

interface Props {
  snapshot: AgentSnapshot | null;
}

export const MetricsStrip: React.FC<Props> = ({ snapshot }) => {
  if (!snapshot) return null;
  const m = snapshot.metrics || { steps: 0 };
  const gs = snapshot.game_state || ({} as any);
  const partyCount = gs.party_count || 0;

  return (
    <div className="metrics-strip">
      <div className="metric">
        <div className="metric-label">STEP</div>
        <div className="metric-value">{m.steps ?? snapshot.step ?? 0}</div>
      </div>
      <div className="metric">
        <div className="metric-label">BADGES</div>
        <div className="metric-value">{m.badges_earned ?? 0}</div>
      </div>
      <div className="metric">
        <div className="metric-label">BATTLES</div>
        <div className="metric-value">{m.battles_won ?? 0}</div>
      </div>
      <div className="metric">
        <div className="metric-label">PARTY</div>
        <div className="metric-value">{partyCount}</div>
      </div>
      <div className="metric">
        <div className="metric-label">REPLAN</div>
        <div className="metric-value">{snapshot.replan_count ?? 0}</div>
      </div>
    </div>
  );
};
