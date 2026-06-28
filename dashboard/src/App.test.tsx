/**
 * Component tests that drive the *shipped* React code + demo data.
 * Assert visible populated elements (action, subgoal, history, metrics, screenshot area, issues).
 * These are real render tests, not mocks of the UI logic.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import App from './App';

describe('Dashboard UI (real components + demo data)', () => {
  beforeEach(() => {
    // Ensure clean
    document.body.innerHTML = '';
  });

  it('renders main sections and loads demoNormal data into visible elements', () => {
    render(<App />);

    // Key structural elements from shipped components (use All because pane headers repeat in content)
    expect(screen.getAllByText(/Game Frame/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Last Action/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Active Subgoal/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Position/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Recent History/i).length).toBeGreaterThan(0);

    // Load the normal demo explicitly via button
    const normalBtn = screen.getByRole('button', { name: /Normal explore/i });
    fireEvent.click(normalBtn);

    // Now assert populated data from the shipped demoNormal
    // last_action "navigate_right" formatted
    expect(screen.getByText(/navigate right/i)).toBeInTheDocument();
    // active_subgoal - use the prominent div (first match)
    const subgoals = screen.getAllByText(/Leave New Bark Town east/i);
    expect(subgoals.length).toBeGreaterThan(0);
    // history entries from demo (real content from demoNormal) - use partial match
    const hist = screen.getAllByText(/navigate:right@8/i);
    expect(hist.length).toBeGreaterThan(0);
    // position text (multiple ok)
    expect(screen.getAllByText(/New Bark Town/i).length).toBeGreaterThan(0);
  });

  it('renders replan + high-stuck demo and surfaces issue visuals', () => {
    render(<App />);

    const replanBtn = screen.getByRole('button', { name: /Replan \+ high stuck/i });
    fireEvent.click(replanBtn);

    // critic verdict badge / replan (use getAll to tolerate multiple)
    const replanNodes = screen.getAllByText(/replan/i);
    expect(replanNodes.length).toBeGreaterThan(0);
    // stuck count shows high
    expect(screen.getByText(/STUCK: 7/i)).toBeInTheDocument();
    // subgoal + action still visible
    const subgoalMatches = screen.getAllByText(/Talk to Mom and leave/i);
    expect(subgoalMatches.length).toBeGreaterThan(0);
    // history has loop-ish entries
    const loopFlags = screen.getAllByText(/LOOP/i);
    expect(loopFlags.length).toBeGreaterThan(0);
    // critic_notes rendered
    expect(screen.getByText(/Detected loop or high stuck count/i)).toBeInTheDocument();
  });

  it('screenshot pane, metrics strip and status strip are populated', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /Bootstrap \+ error/i }));

    // screenshot container exists and has overlay or image
    const frame = screen.getByAltText(/Current emulator screenshot/i);
    expect(frame).toBeInTheDocument();

    // metrics numbers
    expect(screen.getByText('STEP')).toBeInTheDocument();
    // badges etc
    expect(screen.getByText('12')).toBeInTheDocument(); // step in demoError

    // status badges
    expect(screen.getByText(/PHASE:/i)).toBeInTheDocument();
  });
});
