---
phase: 4
plan: 4
wave: 2
---

# Plan 4.4: Trust Manager & Action Orchestration

## Objective
Implement the adaptive trust model and integrate the action pipeline into the event bus.

## Context
- .gsd/DECISIONS.md
- core/engine/brain.py

## Tasks

<task type="auto">
  <name>Trust Manager</name>
  <files>core/state/trust.py</files>
  <action>
    - Implement a persistent trust score per action type.
    - Handle Level 1 (Always Confirm) logic for the first 5-10 uses.
    - Implement the confirmation request loop (Voice/UI).
  </action>
  <verify>python core/state/trust.py (check if trust increases after confirmation)</verify>
  <done>Trust manager correctly gates actions based on historical reliability.</done>
</task>

<task type="auto">
  <name>Action Orchestrator</name>
  <files>core/engine/action_orchestrator.py</files>
  <action>
    - Subscribe to "ACTION_REQUESTED" from Brain.
    - Orchestrate the Flow: Resolve â†’ Trust Check â†’ (Optional Confirm) â†’ Highlight â†’ Execute â†’ Re-verify.
    - Emit "ACTION_STARTED" and "ACTION_COMPLETED".
  </action>
  <verify>python core/engine/action_orchestrator.py</verify>
  <done>Action pipeline is fully integrated and follows safety guardrails.</done>
</task>

## Success Criteria
- [ ] Actions require confirmation until trust is established.
- [ ] Brain's "act" intent successfully triggers real, safe system actions.
