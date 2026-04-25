---
phase: 1
plan: 3
wave: 2
---

# Plan 1.3: Hybrid UI Detection (OCR + UIAutomation)

## Objective
Implement the hybrid vision system combining structured UI tree parsing with fallback OCR.

## Context
- .gsd/DECISIONS.md
- core/vision/capture.py

## Tasks

<task type="auto">
  <name>UI Automation Module</name>
  <files>core/ui/automation.py</files>
  <action>
    - Use `comtypes` to extract structured UI elements from the active window.
    - Emit "UI_UPDATED" event with element tree and metadata.
    - If extraction is empty or fails, flag for OCR fallback.
  </action>
  <verify>python core/ui/automation.py</verify>
  <done>Returns UI objects and emits event; flags fallback when needed.</done>
</task>

<task type="auto">
  <name>OCR Processing Module</name>
  <files>core/ocr/engine.py</files>
  <action>
    - Integrate `pytesseract` with OpenCV preprocessing.
    - Implement Control Rules:
      - Only run if "SCREEN_UPDATED" + (UIAutomation fallback or Error detected).
      - Add a 2-3 second cooldown to prevent OCR spam.
      - Limit OCR to active regions.
    - Emit "TEXT_UPDATED" event.
  </action>
  <verify>python core/ocr/engine.py</verify>
  <done>OCR runs only under specified conditions and emits TEXT_UPDATED.</done>
</task>

## Success Criteria
- [ ] Structured UI data extracted via Windows API.
- [ ] OCR provides fallback text for non-standard UI elements.
