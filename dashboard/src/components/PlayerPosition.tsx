import React from "react";
import type { AgentSnapshot } from "../lib/agentTypes";
import { formatPosition } from "../lib/agentTypes";

interface Props {
  snapshot: AgentSnapshot | null;
}

export const PlayerPosition: React.FC<Props> = ({ snapshot }) => {
  if (!snapshot) return null;
  const gs = snapshot.game_state || ({} as any);
  const p = gs.player || { map_name: "unknown", x: 0, y: 0, map_group: 0, map_id: 0 };
  const badges = (gs.johto_badges || 0) + (gs.kanto_badges || 0);

  return (
    <div className="pane position-pane">
      <div className="pane-header">Position</div>
      <div className="pos-main">{formatPosition(gs)}</div>
      <div className="pos-meta">
        map {p.map_group}:{p.map_id} &nbsp; badges: {badges}
        {gs.battle?.in_battle && " • IN BATTLE"}
      </div>
    </div>
  );
};
