/**
 * Canned demo AgentSnapshot data (ROM-free) matching the acceptance criteria.
 * Includes a normal progressing step + one with replan + high stuck + error case.
 * Used by UI when no live /api/state is available or for "Load Demo" buttons.
 */

import type { AgentSnapshot } from "./agentTypes";

const baseGameState = {
  player: {
    map_group: 24,
    map_id: 4,
    map_name: "New Bark Town",
    x: 8,
    y: 12,
    facing: 0,
    money: 3000,
  },
  party: [
    { species_name: "Chikorita", level: 5, hp: 20, max_hp: 20 },
  ],
  party_count: 1,
  battle: {
    in_battle: false,
    phase: "none",
    player_active_hp: 20,
    player_active_max_hp: 20,
    enemy_species_name: "",
    enemy_hp: 0,
    enemy_max_hp: 0,
  },
  in_menu: false,
  in_text_box: false,
  johto_badges: 0,
  kanto_badges: 0,
  badge_names: [],
};

export const demoNormal: AgentSnapshot = {
  step: 27,
  metrics: { steps: 27, badges_earned: 0, battles_won: 0 },
  last_action: "navigate_right",
  last_action_result: {
    direction: "right",
    target: [12, 12],
    path_length: 4,
    candidates: ["right", "down"],
  },
  active_subgoal: "Leave New Bark Town east toward Route 29",
  current_plan: [
    "Current area: New Bark Town",
    "Visit Professor Elm's lab and choose a starter Pokemon",
    "Active subgoal: Leave New Bark Town east toward Route 29",
  ],
  phase: "explore",
  critic_verdict: "proceed",
  critic_notes: "Action acceptable",
  stuck_count: 1,
  short_term_history: [
    "navigate:left@7,12",
    "navigate:up@7,11",
    "navigate:right@8,11",
    "navigate:right@9,11",
    "navigate:right@10,11",
    "navigate:down@10,12",
    "navigate:right@11,12",
  ],
  game_state: {
    ...baseGameState,
    player: { ...baseGameState.player, x: 8, y: 12 },
  },
  next_node: "navigator",
  screenshot_url: "/demo-screenshot.png",
  timestamp: "2026-06-28T10:00:00Z",
};

export const demoReplanStuck: AgentSnapshot = {
  step: 58,
  metrics: { steps: 58, badges_earned: 0, battles_won: 1 },
  last_action: "navigate_up",
  last_action_result: {
    direction: "up",
    target: [5, 4],
    path_length: 0,
    candidates: ["up", "left"],
  },
  active_subgoal: "Talk to Mom and leave through the front door to New Bark Town",
  current_plan: [
    "Current area: Player's House 1F",
    "Leave player house",
    "Active subgoal: Talk to Mom and leave through the front door to New Bark Town",
  ],
  phase: "explore",
  critic_verdict: "replan",
  critic_notes: "Detected loop or high stuck count",
  stuck_count: 7,
  replan_count: 2,
  short_term_history: [
    "navigate:left@3,5",
    "navigate:right@4,5",
    "navigate:left@3,5",
    "navigate:right@4,5",
    "navigate:up@4,4",
    "navigate:down@4,5",
    "navigate:left@3,5",
  ],
  game_state: {
    ...baseGameState,
    player: {
      ...baseGameState.player,
      map_group: 24,
      map_id: 1,
      map_name: "Player's House 1F",
      x: 3,
      y: 5,
    },
  },
  next_node: "planner",
  error: "",
  screenshot_url: "/demo-boot.png",
  timestamp: "2026-06-28T10:05:00Z",
};

export const demoError: AgentSnapshot = {
  step: 12,
  metrics: { steps: 12, badges_earned: 0, battles_won: 0 },
  last_action: "bootstrap_a",
  last_action_result: { button: "a", bootstrap_index: 3 },
  active_subgoal: "intro sequence",
  current_plan: ["Start new game"],
  phase: "bootstrap",
  critic_verdict: "proceed",
  stuck_count: 0,
  short_term_history: ["bootstrap_a@title", "bootstrap_a@title"],
  game_state: {
    ...baseGameState,
    player: { ...baseGameState.player, map_name: "TITLE", x: 0, y: 0 },
  },
  next_node: "bootstrap",
  error: "LLM call failed: timeout contacting openrouter",
  screenshot_url: "/demo-boot.png",
  timestamp: "2026-06-28T09:55:00Z",
};

export const allDemos = [
  { label: "Normal explore", data: demoNormal },
  { label: "Replan + high stuck", data: demoReplanStuck },
  { label: "Bootstrap + error", data: demoError },
];

export function getInitialDemo() {
  return { ...demoNormal };
}
