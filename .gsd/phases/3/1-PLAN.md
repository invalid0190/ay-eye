---
phase: 3
plan: 1
wave: 1
---

# Plan 3.1: Hotkey Manager & TTS Engine

## Objective
Implement the global hotkey for push-to-talk and the lightweight TTS engine with immediate interrupt support.

## Context
- .gsd/DECISIONS.md
- core/engine/event_bus.py

## Tasks

<task type="auto">
  <name>Hotkey Manager</name>
  <files>core/engine/hotkeys.py</files>
  <action>
    - Use `keyboard` library to implement a global hook for "Alt+Z".
    - Track "Pressed" and "Released" states for Push-to-Talk.
    - Emit "HOTKEY_PRESSED" and "HOTKEY_RELEASED" events.
  </action>
  <verify>python -m core.engine.hotkeys (should log press/release events)</verify>
  <done>Alt+Z is correctly detected globally and emits events.</done>
</task>

<task type="auto">
  <name>TTS Engine with Interrupts</name>
  <files>core/engine/tts.py</files>
  <action>
    - Integrate `pyttsx3`.
    - Configure speech rate to 1.2x.
    - Implement a thread-safe `stop()` method.
    - Subscribe to "USER_INPUT_DETECTED" (from Phase 1/3) to trigger `stop()`.
  </action>
  <verify>python core/engine/tts.py (should speak a test string and stop if a key is pressed)</verify>
  <done>TTS speaks at correct rate and stops immediately on interrupt.</done>
</task>

## Success Criteria
- [ ] Global hotkey Alt+Z works reliably.
- [ ] TTS can be stopped mid-sentence via code call.
