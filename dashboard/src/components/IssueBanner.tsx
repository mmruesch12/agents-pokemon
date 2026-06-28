import React from "react";
import type { AgentSnapshot, IssueFlag } from "../lib/agentTypes";
import { detectIssues } from "../lib/agentTypes";

interface Props {
  snapshot: AgentSnapshot | null;
}

const messages: Record<IssueFlag, string> = {
  high_stuck: "High stuck count — agent may replan soon or is looping.",
  replan: "Critic requested replan — plan or navigation is being reconsidered.",
  error: "Error recorded in agent state.",
  bootstrap: "Bootstrap / intro sequence in progress (expected early).",
  battle: "In battle phase.",
};

export const IssueBanner: React.FC<Props> = ({ snapshot }) => {
  if (!snapshot) return null;
  const issues = detectIssues(snapshot);
  if (issues.length === 0) return null;

  // surface highest priority
  const primary = issues.includes("replan")
    ? "replan"
    : issues.includes("high_stuck")
    ? "high_stuck"
    : issues.includes("error")
    ? "error"
    : issues[0];

  return (
    <div className={`issue-banner ${primary}`}>
      <strong>⚠ {primary.toUpperCase().replace("_", " ")}</strong>
      {" — "}
      {messages[primary]}
      {issues.length > 1 && ` (+${issues.length - 1} more)`}
    </div>
  );
};
