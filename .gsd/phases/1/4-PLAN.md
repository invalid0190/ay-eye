---
phase: 1
plan: 4
wave: 3
---

# Plan 1.4: Main Loop & Smart Triggers

## Objective
Orchestrate all Phase 1 modules into a high-performance, multi-threaded main loop with smart trigger logic.

## Context
- .gsd/DECISIONS.md
- core/state/manager.py

## Tasks

<task type="auto">
  <name>Smart Trigger Engine</name>
  <files>core/engine/triggers.py</files>
  <action>
    - Implement specific trigger types with cooldowns:
      - ERROR_TRIGGER: OCR/UI contains error keywords.
      - IDLE_TRIGGER: No input events for 5-10s.
      - REPETITION_TRIGGER: Multiple identical actions.
      - CONTEXT_CHANGE_TRIGGER: App/Window switch.
    - Emit "AI_TRIGGERED" event (do NOT call AI directly).
  </action>
  <verify>python core/engine/triggers.py</verify>
  <done>Triggers emit events based on complex state conditions.</done>
</task>

<task type="auto">
  <name>Main Loop Orchestrator</name>
  <files>main.py, core/engine/orchestrator.py</files>
  <action>
    - Coordinate modules via EventBus.
    - Implement logging for all events and trigger activations.
    - Ensure CPU usage remains < 30% by skipping idle cycles.
  </action>
  <verify>python main.py --dry-run</verify>
  <done>Orchestrator manages the event flow and stays within performance limits.</done>
</task>

## Success Criteria
- [ ] Multi-threaded loop runs with <500ms processing latency.
- [ ] AI trigger fires correctly on "Smart Trigger" events.
- [ ] System handles privacy blacklisting by pausing all processing.
