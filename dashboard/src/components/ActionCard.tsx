import React from "react";
import type { AgentSnapshot } from "../lib/agentTypes";
import { formatLastAction } from "../lib/agentTypes";

interface Props {
  snapshot: AgentSnapshot | null;
}

export const ActionCard: React.FC<Props> = ({ snapshot }) => {
  if (!snapshot) return <div className="pane">No action data</div>;

  const action = snapshot.last_action || "—";
  const res = snapshot.last_action_result || {};
  const specialist =
    action.startsWith("bootstrap_") || snapshot.phase === "bootstrap"
      ? "bootstrap"
      : action.startsWith("navigate_")
      ? "navigator"
      : action.startsWith("battle_")
      ? "battler"
      : snapshot.phase === "plan" || snapshot.critic_verdict === "replan"
      ? "planner"
      : "supervisor";

  return (
    <div className="pane action-card">
      <div className="pane-header">Last Action</div>
      <div className="action-main">
        <span className="specialist">{specialist}</span>
        <span className="arrow">→</span>
        <span className="action-name">{formatLastAction(action)}</span>
      </div>

      {Object.keys(res).length > 0 && (
        <div className="action-result">
          {res.direction && <span>dir: <b>{res.direction}</b></span>}
          {res.target && <span>target: [{res.target.join(",")}]</span>}
          {res.path_length != null && <span>path: {res.path_length}</span>}
          {res.reason && <span>reason: {res.reason}</span>}
          {res.action && <span>action: {res.action}</span>}
          {res.phase && <span>phase: {res.phase}</span>}
          {res.button && <span>button: {res.button}</span>}
        </div>
      )}

      {snapshot.critic_notes && (
        <div className="critic-note">critic: {snapshot.critic_notes}</div>
      )}

      {snapshot.error && <div className="error-inline">⚠ {snapshot.error}</div>}
    </div>
  );
};
