import React from "react";
import type { AgentSnapshot, IssueFlag } from "../lib/agentTypes";
import { detectIssues } from "../lib/agentTypes";

interface Props {
  snapshot: AgentSnapshot | null;
}

const phaseColor = (phase: string) => {
  if (phase === "bootstrap") return "phase-bootstrap";
  if (phase === "battle") return "phase-battle";
  return "phase-explore";
};

const verdictClass = (verdict: string) => {
  const v = (verdict || "").toLowerCase();
  if (v === "replan") return "verdict-replan";
  if (v === "caution") return "verdict-caution";
  return "verdict-proceed";
};

export const StatusStrip: React.FC<Props> = ({ snapshot }) => {
  if (!snapshot) return null;
  const issues: IssueFlag[] = detectIssues(snapshot);
  const stuck = snapshot.stuck_count ?? 0;
  const isHighStuck = stuck >= 5;

  return (
    <div className="status-strip">
      <div className={`badge phase ${phaseColor(snapshot.phase)}`}>
        PHASE: {snapshot.phase || "explore"}
      </div>

      <div className={`badge verdict ${verdictClass(snapshot.critic_verdict)}`}>
        CRITIC: {snapshot.critic_verdict || "proceed"}
      </div>

      <div className={`badge stuck ${isHighStuck ? "stuck-high" : ""}`}>
        STUCK: {stuck}
        {isHighStuck && " ⚠"}
      </div>

      {snapshot.replan_count != null && snapshot.replan_count > 0 && (
        <div className="badge replan">REPLAN×{snapshot.replan_count}</div>
      )}

      {issues.includes("error") && <div className="badge error">ERROR</div>}
      {snapshot.next_node && <div className="badge next">→ {snapshot.next_node}</div>}
    </div>
  );
};
