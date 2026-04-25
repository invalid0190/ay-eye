---
phase: 4
plan: 1
wave: 1
---

# Plan 4.1: Kill Switch & PyQt6 Visual Overlay

## Objective
Implement the safety "Kill Switch" and the PyQt6 transparent overlay to provide visual feedback before actions.

## Context
- .gsd/DECISIONS.md

## Tasks

<task type="auto">
  <name>Safety Kill Switch</name>
  <files>core/engine/hotkeys.py</files>
  <action>
    - Add "Ctrl+Shift+X" to the hotkey manager.
    - Implement a high-priority "EMERGENCY_STOP" event.
    - Ensure it kills any active action threads immediately.
  </action>
  <verify>python -m core.engine.hotkeys (test if Ctrl+Shift+X triggers the event)</verify>
  <done>Emergency kill switch is active and responsive.</done>
</task>

<task type="auto">
  <name>Visual Overlay (PyQt6)</name>
  <files>core/ui/overlay.py</files>
  <action>
    - Initialize a transparent, click-through PyQt6 window.
    - Implement `highlight_element(x, y, w, h, duration)` method.
    - Draw a colored bounding box over specified coordinates.
  </action>
  <verify>python core/ui/overlay.py (should flash a red box on the screen)</verify>
  <done>Visual feedback overlay is capable of highlighting elements.</done>
</task>

## Success Criteria
- [ ] Emergency stop stops all actions instantly.
- [ ] Visual overlay highlights screen regions accurately.
