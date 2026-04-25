---
phase: 5
plan: 2
wave: 1
---

# Plan 5.2: Base GUI Framework (PyQt6)

## Objective
Establish the visual foundation for ay-eye using a styled PyQt6 window system with glassmorphism.

## Context
- .gsd/DECISIONS.md
- core/ui/overlay.py

## Tasks

<task type="auto">
  <name>UI Theme Engine</name>
  <files>core/ui/theme.py</files>
  <action>
    - Define QSS (Qt Style Sheets) for the "Terminal Dark + Glass" aesthetic.
    - Set background colors (near black, high alpha).
    - Set accent colors (cyan/soft blue).
    - Implement font selection (Inter/Roboto or system monospaced).
  </action>
  <verify>python core/ui/theme.py (display a test themed widget)</verify>
  <done>UI theme is defined and visually matches the dev copilot identity.</done>
</task>

<task type="auto">
  <name>Main Dashboard Window</name>
  <files>core/ui/dashboard.py</files>
  <action>
    - Create the base `AyEyeDashboard` class.
    - Set window properties: Frameless, AlwaysOnTop, ToolWindow.
    - Implement basic position management (bottom-right corner).
    - Integrate with `QTimer` for smooth animations (fade/slide).
  </action>
  <verify>python core/ui/dashboard.py (should show a minimal themed window in the corner)</verify>
  <done>Base dashboard window is operational and styled.</done>
</task>

## Success Criteria
- [ ] Window follows the "Terminal Dark + Glass" aesthetic.
- [ ] Dashboard is non-intrusive but visible.
