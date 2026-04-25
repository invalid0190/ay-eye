# REQUIREMENTS.md

## Format
| ID | Requirement | Source | Status |
|----|-------------|--------|--------|
| REQ-VIS-01 | Capture screen every 1-2 seconds using `mss` | SPEC goal 1 | Pending |
| REQ-VIS-02 | Extract text via `pytesseract` and UI structure via Windows Accessibility API | SPEC goal 1 | Pending |
| REQ-AI-01 | Integrate Ollama (Llama 3 8B) for local reasoning | SPEC goal 2 | Pending |
| REQ-AI-02 | Implement prompt system including screen context and user history | SPEC goal 2 | Pending |
| REQ-VCE-01 | Local wake-word detection ("Hey ay-eye") | SPEC goal 2 | Pending |
| REQ-VCE-02 | STT using OpenAI Whisper (local base model) | SPEC goal 2 | Pending |
| REQ-VCE-03 | TTS using pyttsx3 or Coqui for natural voice feedback | SPEC goal 2 | Pending |
| REQ-AUTO-01 | Execute mouse/keyboard actions via `pyautogui` | SPEC goal 4 | Pending |
| REQ-AUTO-02 | Command parser to map AI intent to Python actions | SPEC goal 4 | Pending |
| REQ-AUTO-03 | Safety confirmation modal/voice query before dangerous actions | SPEC goal 4 | Pending |
| REQ-MEM-01 | ChromaDB integration for semantic conversation retrieval | SPEC goal 5 | Pending |
| REQ-GUI-01 | PyQt6 floating window with status indicators (Thinking/Listening) | SPEC goal 3 | Pending |
| REQ-GUI-02 | Transparent overlay to highlight UI elements during automation | SPEC goal 3 | Pending |
