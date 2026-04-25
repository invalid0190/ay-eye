---
phase: 2
plan: 4
wave: 3
---

# Plan 2.4: Decision Engine & Brain Orchestration

## Objective
Implement the "Brain" decision logic and integrate it into the main event-driven loop.

## Context
- .gsd/DECISIONS.md
- core/engine/orchestrator.py

## Tasks

<task type="auto">
  <name>Decision Engine Gating</name>
  <files>core/engine/decision_engine.py</files>
  <action>
    - Implement the gating logic for AI calls:
      - Confidence > 0.7 from Trigger Engine.
      - 10s Cooldown between calls.
      - Filter out "Passive Reading" (based on scroll/UI staticity).
    - Implement the Post-Processing response mode selector (Silent vs UI vs Voice).
  </action>
  <verify>python core/engine/decision_engine.py</verify>
  <done>AI is only called on meaningful triggers; response modes are correctly chosen.</done>
</task>

<task type="auto">
  <name>Brain Integration</name>
  <files>main.py, core/engine/brain.py</files>
  <action>
    - Create a `Brain` module that subscribes to "AI_TRIGGERED".
    - Flow: Trigger â†’ Decision Engine â†’ Context Builder â†’ Memory Fetch â†’ LLM Bridge â†’ JSON Parser â†’ Event: "BRAIN_RESPONDED".
    - Update `main.py` to handle the new "BRAIN_RESPONDED" event.
  </action>
  <verify>python main.py (simulated trigger should log Brain response)</verify>
  <done>Phase 1 Vision and Phase 2 Brain are fully integrated via the Event Bus.</done>
</task>

## Success Criteria
- [ ] AI is called only when the user is likely stuck or an error occurs.
- [ ] Brain outputs structured JSON consistently via the event bus.
- [ ] Response modes (Voice/UI) are correctly filtered by confidence.
