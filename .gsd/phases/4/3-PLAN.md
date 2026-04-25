---
phase: 4
plan: 3
wave: 2
---

# Plan 4.3: Target Resolver (UI/OCR Mapping)

## Objective
Convert abstract Brain targets (e.g., "Login Button") into concrete screen coordinates.

## Context
- .gsd/DECISIONS.md
- core/state/models.py

## Tasks

<task type="auto">
  <name>UI Target Resolver</name>
  <files>core/engine/resolver.py</files>
  <action>
    - Implement matching logic using `SystemState`:
      1. Search `ui_elements` for matching name/role.
      2. Fallback to `ocr_text` matches if UIAutomation fails.
    - Resolve bounding boxes to center-point screen coordinates.
    - Implement the "Ambiguity Check": If >1 match in active window, return `AMBIGUOUS`.
  </action>
  <verify>python core/engine/resolver.py (match "File" in a sample state)</verify>
  <done>Resolver accurately maps UI labels to screen coordinates.</done>
</task>

## Success Criteria
- [ ] Resolver consistently finds coordinates for labeled elements.
- [ ] Multiple matches are correctly flagged as ambiguous.
