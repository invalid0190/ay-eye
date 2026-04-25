---
phase: 2
plan: 2
wave: 1
---

# Plan 2.2: Context Distiller & Prompt Builder

## Objective
Convert raw Phase 1 screen state into a distilled, token-efficient prompt for the Brain.

## Context
- .gsd/DECISIONS.md
- core/state/models.py

## Tasks

<task type="auto">
  <name>Context Distiller</name>
  <files>core/engine/context_builder.py</files>
  <action>
    - Implement rule-based filtering: Remove duplicate text, prioritize UI elements (Buttons, Inputs, Errors).
    - Implement smart truncation for large OCR results.
    - Format distilled state into a clean JSON-like structure for the prompt.
  </action>
  <verify>python -m core.engine.context_builder (should print a distilled version of a sample State object)</verify>
  <done>Context Distiller significantly reduces token count while preserving critical UI info.</done>
</task>

<task type="auto">
  <name>Prompt Template System</name>
  <files>core/templates/prompts.py</files>
  <action>
    - Implement 3-layer template system:
      1. System: ay-eye identity and JSON rules.
      2. Context: Distilled screen state + Memory (Phase 2.3).
      3. Task: The specific trigger condition.
    - Ensure prompts explicitly demand the JSON output schema.
  </action>
  <verify>python -c "from core.templates.prompts import build_prompt; print(build_prompt(state, trigger))"</verify>
  <done>Prompt builder generates consistent, high-quality instructions for the LLM.</done>
</task>

## Success Criteria
- [ ] Context is filtered down to essential elements only.
- [ ] Prompt templates reliably steer the model toward structured responses.
