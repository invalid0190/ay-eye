---
phase: 3
plan: 4
wave: 2
---

# Plan 3.4: Faster-Whisper STT Integration

## Objective
Integrate the optimized faster-whisper engine for real-time transcription.

## Context
- .gsd/DECISIONS.md
- core/vision/audio_capture.py

## Tasks

<task type="auto">
  <name>Whisper Engine Setup</name>
  <files>core/ocr/stt_engine.py</files>
  <action>
    - Integrate `faster-whisper`.
    - Load the "base" or "small" model (quantized for 16GB RAM).
    - Implement transcription logic for audio buffers.
    - Emit "VOICE_INPUT_RECEIVED" with the result.
  </action>
  <verify>python core/ocr/stt_engine.py (should transcribe a test audio file)</verify>
  <done>Transcriptions are accurate and complete in <2s.</done>
</task>

<task type="auto">
  <name>Voice-to-Brain Integration</name>
  <files>core/engine/brain.py, core/ocr/stt_engine.py</files>
  <action>
    - Ensure Brain subscribes to "VOICE_INPUT_RECEIVED".
    - Treat voice input as a high-priority "USER_DIRECT_INPUT" trigger.
  </action>
  <verify>Hold Alt+Z, speak, and check if Brain processes the intent.</verify>
  <done>User voice commands are correctly interpreted by the Brain.</done>
</task>

## Success Criteria
- [ ] STT engine provides fast local transcription.
- [ ] Voice commands successfully trigger Brain reasoning.
