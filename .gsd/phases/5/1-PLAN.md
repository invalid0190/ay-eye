---
phase: 5
plan: 1
wave: 1
---

# Plan 5.1: Global Identity Migration ("ay-eye")

## Objective
Systematically rename all assistant references and refactor the persona to match the "ay-eye" technical copilot profile.

## Context
- .gsd/DECISIONS.md
- core/engine/brain.py
- core/engine/context_builder.py
- core/engine/voice_controller.py

## Tasks

<task type="auto">
  <name>Codebase Identity Sweep</name>
  <action>
    - Global find and replace: "Jarvis" -> "ay-eye".
    - Global find and replace: "Assistant" (where it refers to the AI) -> "ay-eye".
    - Update all log prefixes and internal comments.
  </action>
  <verify>grep -r "Jarvis" . (should return zero results outside of .gsd documentation)</verify>
  <done>System-wide rename to 'ay-eye' is complete.</done>
</task>

<task type="auto">
  <name>Brain & Voice Retoning</name>
  <files>core/engine/context_builder.py, core/engine/brain.py, core/engine/voice_controller.py</files>
  <action>
    - Update `System Prompt` in `context_builder.py` to enforce the calm, minimal, technical tone.
    - Instruct LLM to use noun-verb phrasing.
    - Remove theatrical filler words from pre-defined responses.
  </action>
  <verify>python -m core.engine.context_builder (should show updated system prompt)</verify>
  <done>ay-eye's persona is calibrated for technical precision.</done>
</task>

## Success Criteria
- [ ] No "Jarvis" references remain in the active codebase.
- [ ] LLM output and Voice output use the new minimal tone.
