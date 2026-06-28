import React from "react";
import type { AgentSnapshot } from "../lib/agentTypes";

interface Props {
  snapshot: AgentSnapshot | null;
}

export const SubgoalPanel: React.FC<Props> = ({ snapshot }) => {
  if (!snapshot) return null;
  const plan = snapshot.current_plan || [];
  const active = snapshot.active_subgoal || "—";

  return (
    <div className="pane subgoal-panel">
      <div className="pane-header">Active Subgoal</div>
      <div className="active-subgoal">{active}</div>

      {plan.length > 0 && (
        <>
          <div className="subhead">Current Plan</div>
          <ol className="plan-list">
            {plan.map((p, i) => (
              <li key={i} className={p.includes(active) ? "active-item" : ""}>
                {p}
              </li>
            ))}
          </ol>
        </>
      )}

      {snapshot.subgoals && snapshot.subgoals.length > 0 && (
        <>
          <div className="subhead">Subgoals</div>
          <ul className="subgoal-list">
            {snapshot.subgoals.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
};
