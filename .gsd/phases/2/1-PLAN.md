---
phase: 2
plan: 1
wave: 1
---

# Plan 2.1: Ollama Bridge & JSON Healing Parser

## Objective
Implement the communication bridge to Ollama and the robust JSON parsing logic to ensure reliable structured data from local LLMs.

## Context
- .gsd/DECISIONS.md
- core/utils/logger.py

## Tasks

<task type="auto">
  <name>Ollama Bridge</name>
  <files>core/engine/llm_bridge.py</files>
  <action>
    - Implement a wrapper for Ollama's API.
    - Support model selection (Llama3/Mistral) and timeout handling.
    - Add a simple Cloud API fallback (placeholder for Phase 2).
    - Implement a single-retry mechanism for malformed outputs.
  </action>
  <verify>python -m core.engine.llm_bridge (should return a valid response from Ollama)</verify>
  <done>Bridge successfully communicates with local Ollama and handles retries.</done>
</task>

<task type="auto">
  <name>JSON Healing Parser</name>
  <files>core/utils/json_parser.py</files>
  <action>
    - Write a utility to extract JSON blocks from string responses (using regex).
    - Implement "healing" logic: fix trailing commas, missing closing braces, and unquoted keys.
    - Validate against the Phase 2 output schema (intent, message, actions, confidence).
  </action>
  <verify>python -c "from core.utils.json_parser import heal; print(heal('{ \"intent\": \"act\", }'))"</verify>
  <done>Parser successfully heals common LLM JSON errors and validates schema.</done>
</task>

## Success Criteria
- [ ] LLM bridge successfully communicates with local models.
- [ ] JSON healing parser consistently extracts valid JSON from noisy model output.
