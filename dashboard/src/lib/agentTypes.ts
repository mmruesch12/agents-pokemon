/**
 * TypeScript types mirroring the Python AgentState + GameState for the dashboard.
 * These are view models / wire shapes. Keep in sync with src/graph/state.py and src/state/models.py.
 */

export interface PlayerState {
  map_group: number;
  map_id: number;
  map_name: string;
  x: number;
  y: number;
  facing: number;
  money: number;
}

export interface BattleState {
  in_battle: boolean;
  phase: string;
  player_active_hp: number;
  player_active_max_hp: number;
  enemy_species_name: string;
  enemy_hp: number;
  enemy_max_hp: number;
}

export interface GameState {
  player: PlayerState;
  party: Array<{ species_name: string; level: number; hp: number; max_hp: number }>;
  party_count: number;
  battle: BattleState;
  in_menu: boolean;
  in_text_box: boolean;
  johto_badges: number;
  kanto_badges: number;
  badge_names: string[];
  map_key?: string;
  position_key?: string;
}

export interface LastActionResult {
  direction?: string;
  target?: [number, number];
  path_length?: number;
  candidates?: string[];
  reason?: string;
  action?: string;
  phase?: string;
  button?: string;
  [key: string]: unknown;
}

export interface Metrics {
  steps: number;
  badges_earned?: number;
  battles_won?: number;
  [key: string]: unknown;
}

export interface AgentSnapshot {
  step?: number;
  metrics: Metrics;
  last_action: string;
  last_action_result: LastActionResult;
  active_subgoal: string;
  current_plan: string[];
  subgoals?: string[];
  phase: string;
  critic_verdict: "proceed" | "replan" | "caution" | string;
  critic_notes?: string;
  stuck_count: number;
  short_term_history: string[];
  game_state: GameState;
  next_node?: string;
  error?: string;
  replan_count?: number;
  maps_visited?: string[];
  // derived / server provided
  screenshot_url?: string; // relative or absolute for <img src>
  timestamp?: string;
}

export type IssueFlag =
  | "high_stuck"
  | "replan"
  | "error"
  | "battle"
  | "bootstrap";

export function detectIssues(state: AgentSnapshot): IssueFlag[] {
  const issues: IssueFlag[] = [];
  const stuck = state.stuck_count ?? 0;
  const verdict = (state.critic_verdict || "").toLowerCase();
  const action = state.last_action || "";
  const phase = state.phase || "";

  if (stuck >= 5) issues.push("high_stuck");
  if (verdict === "replan") issues.push("replan");
  if (state.error) issues.push("error");
  if (phase === "bootstrap" || action.startsWith("bootstrap_")) issues.push("bootstrap");
  if (phase === "battle" || action.startsWith("battle_")) issues.push("battle");
  return issues;
}

export function formatPosition(gs: GameState | null | undefined): string {
  const p = gs?.player;
  if (!p) return "unknown (0,0)";
  return `${p.map_name || "unknown"} (${p.x ?? 0},${p.y ?? 0})`;
}

export function formatLastAction(action: string): string {
  if (!action) return "none";
  return action.replace(/_/g, " ");
}

export function shortHistory(history: string[], limit = 12): string[] {
  return [...history].slice(-limit).reverse(); // newest first
}
