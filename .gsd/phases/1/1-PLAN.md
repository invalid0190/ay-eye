---
phase: 1
plan: 1
wave: 1
---

# Plan 1.1: State Manager & Window Detection

## Objective
Establish the foundational data structure for the assistant's state and implement the active window detection logic with monitor awareness.

## Context
- .gsd/SPEC.md
- .gsd/DECISIONS.md

## Tasks

<task type="auto">
  <name>Initialize Event Bus & Logging</name>
  <files>core/engine/event_bus.py, core/utils/logger.py</files>
  <action>
    - Implement a simple thread-safe `EventBus` (Pub/Sub).
    - Setup a structured logger that records event emissions, trigger activations, and processing times.
  </action>
  <verify>python -c "from core.engine.event_bus import bus; bus.subscribe('TEST', lambda x: print(x)); bus.publish('TEST', 'Hello')"</verify>
  <done>EventBus handles pub/sub correctly; logs are structured and readable.</done>
</task>

<task type="auto">
  <name>Initialize State Manager</name>
  <files>core/state/manager.py, core/state/models.py</files>
  <action>
    - Create a thread-safe `CurrentState` singleton.
    - Define Pydantic models for the schema: app, window, monitor, ui_elements, ocr_text, last_frame_hash, last_update_time.
    - Integrate with EventBus: Publish "STATE_UPDATED" on change.
  </action>
  <verify>python -c "from core.state.manager import CurrentState; s = CurrentState(); print(s.get_state().dict())"</verify>
  <done>State Manager implements the requested schema and is thread-safe.</done>
</task>

<task type="auto">
  <name>Window & Monitor Detection</name>
  <files>core/vision/window_manager.py</files>
  <action>
    - Use `pygetwindow` or Win32 API to detect the active window.
    - Implement monitor detection based on current cursor position using `pyautogui` or `screeninfo`.
    - Implement the Privacy Blacklist check (Incognito, Password Managers, etc.) to return an "is_sensitive" flag.
  </action>
  <verify>python core/vision/window_manager.py (should print current active window and monitor ID)</verify>
  <done>Returns active window rect and monitor ID; identifies blacklisted apps correctly.</done>
</task>

## Success Criteria
- [ ] Thread-safe State Manager exists.
- [ ] Active window coordinates and monitor ID are correctly identified.
- [ ] Blacklisted apps are detected and trigger a "privacy pause" flag.
