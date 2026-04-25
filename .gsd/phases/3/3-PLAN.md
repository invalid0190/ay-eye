---
phase: 3
plan: 3
wave: 2
---

# Plan 3.3: Audio Capture & Silence Detection

## Objective
Implement high-performance audio capture with silence-based segmentation for the STT engine.

## Context
- .gsd/DECISIONS.md

## Tasks

<task type="auto">
  <name>Audio Capture Module</name>
  <files>core/vision/audio_capture.py</files>
  <action>
    - Use `pyaudio` or `sounddevice` to capture microphone input.
    - Implement a circular buffer for audio data.
    - Link capture activity to the "HOTKEY_PRESSED" event.
  </action>
  <verify>python core/vision/audio_capture.py (should record and save a .wav when hotkey is held)</verify>
  <done>Audio is captured only while the hotkey is active.</done>
</task>

<task type="auto">
  <name>Silence Detection</name>
  <files>core/vision/audio_processor.py</files>
  <action>
    - Implement VAD (Voice Activity Detection) or a simple RMS threshold.
    - Detect silence (0.5-0.7s) to trigger the end of a recording segment.
    - Implement the 10s maximum window fail-safe.
  </action>
  <verify>python core/vision/audio_processor.py</verify>
  <done>Silence detection correctly segments user speech.</done>
</task>

## Success Criteria
- [ ] Audio is captured cleanly with minimal overhead.
- [ ] Silence detection triggers end-of-speech events accurately.
