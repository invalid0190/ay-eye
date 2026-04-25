---
phase: 4
plan: 2
wave: 1
---

# Plan 4.2: Action Executor (PyAutoGUI)

## Objective
Implement the low-level action executor with safety guardrails and sequential processing.

## Context
- .gsd/DECISIONS.md
- core/engine/event_bus.py

## Tasks

<task type="auto">
  <name>PyAutoGUI Wrapper</name>
  <files>core/engine/executor.py</files>
  <action>
    - Implement safe wrappers for: `click`, `typewrite`, `hotkey`, `open_app`.
    - Add fixed delays (100-300ms) between actions.
    - Implement `stop()` method linked to "EMERGENCY_STOP".
    - Add failsafe for `pyautogui` (move mouse to corner to kill).
  </action>
  <verify>python core/engine/executor.py (test basic click/type actions)</verify>
  <done>Action executor performs tasks safely and sequentially.</done>
</task>

<task type="auto">
  <name>App Launcher</name>
  <files>core/utils/launcher.py</files>
  <action>
    - Implement `os.startfile` and `subprocess` logic.
    - Create a basic whitelist of "Safe Apps" (e.g., Notepad, Calculator, Browser).
  </action>
  <verify>python core/utils/launcher.py (launch notepad)</verify>
  <done>Launcher safely opens whitelisted applications.</done>
</task>

## Success Criteria
- [ ] PyAutoGUI actions are executed with controlled delays.
- [ ] Emergency stop works mid-action.
