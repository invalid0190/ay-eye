---
phase: 5
plan: 4
wave: 2
---

# Plan 5.4: Multi-modal Confirmation & Final Polish

## Objective
Finalize the interaction system by linking UI buttons, Voice commands, and Hotkeys to the action confirmation loop.

## Context
- .gsd/DECISIONS.md
- core/engine/action_orchestrator.py

## Tasks

<task type="auto">
  <name>Multi-modal Confirmation Bridge</name>
  <files>core/engine/confirmation_bridge.py</files>
  <action>
    - Link UI Buttons ("Confirm" / "Cancel") to events.
    - Add "Alt + Enter" to `hotkey_manager.py` as a confirmation trigger.
    - Add "Confirm/Go" keyword detection to `voice_controller.py`.
    - Implement the 3-second safety timeout.
  </action>
  <verify>Request action, then confirm via voice, UI, or hotkey.</verify>
  <done>Confirmation system is robust and multi-modal.</done>
</task>

<task type="auto">
  <name>Final System Integration</name>
  <files>main.py</files>
  <action>
    - Ensure all UI events correctly stop/start the main loop threads if necessary.
    - Final polish of log levels and performance metrics.
    - Update `SETUP.md` with GUI requirements (PyQt6).
  </action>
  <verify>Full system run: Hotkey -> Voice -> Brain -> Action Confirmation -> Execution.</verify>
  <done>ay-eye is a complete, polished, and unified ay-eye.</done>
</task>

## Success Criteria
- [ ] User can confirm actions via three different modes.
- [ ] 3s timeout correctly cancels unconfirmed actions.
- [ ] System identity is consistent throughout.
