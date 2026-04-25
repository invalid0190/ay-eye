---
phase: 5
plan: 3
wave: 2
---

# Plan 5.3: Status & Action Panels

## Objective
Implement the functional components of the dashboard: the minimal status bar and the expandable action panel.

## Context
- .gsd/DECISIONS.md
- core/ui/dashboard.py

## Tasks

<task type="auto">
  <name>Minimal Status Bar</name>
  <files>core/ui/components/status_bar.py</files>
  <action>
    - Implement a small label/icon for ay-eye state (Idle, Listening, Acting).
    - Add a "Current App" indicator.
    - Connect to `SystemState` for real-time updates.
  </action>
  <verify>Change active window and see status bar update.</verify>
  <done>Status bar correctly reflects ay-eye's real-time state.</done>
</task>

<task type="auto">
  <name>Expandable Action Panel</name>
  <files>core/ui/components/action_panel.py</files>
  <action>
    - Implement expansion animation logic.
    - Components:
      - Brain Suggestion (Text).
      - Confidence Indicator (Progress bar).
      - Action Preview (List of pending clicks/types).
    - "Confirm" and "Cancel" buttons.
  </action>
  <verify>Trigger an action request and observe the panel expand and display data.</verify>
  <done>Action panel provides clear previews and controls for pending tasks.</done>
</task>

## Success Criteria
- [ ] Status bar is minimal and informative.
- [ ] Action panel expands smoothly when required.
