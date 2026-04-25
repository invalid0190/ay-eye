---
phase: 1
plan: 2
wave: 1
---

# Plan 1.2: Screen Capture & Frame Hashing

## Objective
Implement efficient screen capture for the active window and a hashing mechanism to detect changes, preventing redundant processing.

## Context
- .gsd/DECISIONS.md
- core/state/manager.py

## Tasks

<task type="auto">
  <name>Active Window Capture</name>
  <files>core/vision/capture.py</files>
  <action>
    - Use `mss` to capture the specific bounding box of the active window.
    - Implement a downscaling function to stay within 16GB RAM constraints.
    - Emit "SCREEN_CAPTURED" event with raw frame data.
    - Performance: Target < 100ms capture time.
  </action>
  <verify>python core/vision/capture.py</verify>
  <done>Mss captures the active window and emits the event.</done>
</task>

<task type="auto">
  <name>Frame Change Detection</name>
  <files>core/vision/change_detector.py</files>
  <action>
    - Implement perceptual hashing to compare consecutive captures.
    - If change > threshold: Emit "SCREEN_UPDATED" event.
    - If no change: Skip processing to keep CPU < 30%.
  </action>
  <verify>python core/vision/change_detector.py</verify>
  <done>Emits SCREEN_UPDATED only on meaningful visual changes.</done>
</task>

## Success Criteria
- [ ] Active window capture is isolated and fast.
- [ ] Change detection successfully prevents redundant OCR/AI triggers.
