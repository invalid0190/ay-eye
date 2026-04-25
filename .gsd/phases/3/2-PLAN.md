---
phase: 3
plan: 2
wave: 1
---

# Plan 3.2: Voice Controller & Logic

## Objective
Orchestrate voice behavior by connecting Brain responses to the TTS engine based on confidence and gating rules.

## Context
- .gsd/DECISIONS.md
- core/engine/tts.py

## Tasks

<task type="auto">
  <name>Voice Controller</name>
  <files>core/engine/voice_controller.py</files>
  <action>
    - Subscribe to "BRAIN_RESPONDED".
    - Implement gating logic:
      - confidence > 0.7
      - response["mode"] == "UI_VOICE"
      - not in cooldown.
    - Trigger `tts.speak(message)`.
  </action>
  <verify>python core/engine/voice_controller.py (simulated response should trigger TTS)</verify>
  <done>Voice controller correctly gates speech based on Brain's decision.</done>
</task>

<task type="auto">
  <name>Interrupt Integration</name>
  <files>main.py, core/engine/voice_controller.py</files>
  <action>
    - Subscribe to "KEY_PRESSED" and "MOUSE_CLICKED" events (from main loop).
    - Link these to the `tts.stop()` method.
  </action>
  <verify>Run main.py, trigger speech, then click/type to ensure it stops.</verify>
  <done>Voice interaction is fully interruptible by user actions.</done>
</task>

## Success Criteria
- [ ] Brain responses only speak when high-confidence.
- [ ] Any user physical interaction stops active speech.
