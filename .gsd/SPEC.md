# SPEC.md â€” Project Specification

> **Status**: `FINALIZED`

## Vision
Build "ay-eye", a proactive, ay-eye-like intelligent copilot that runs locally on Windows. Unlike standard chatbots, ay-eye perceives the user's screen in real-time, understands cross-application context, communicates via natural voice, and automates workflows to assist the user as a sidekick rather than a simple interface.

## Goals
1. **Real-Time Perception**: Capture and interpret screen content (OCR + UI Automation) every 1-2 seconds with minimal latency.
2. **Local Intelligence**: Run a multi-modal agent loop using local LLMs (Ollama) and local STT/TTS (Whisper/Coqui) on a 16GB RAM/iGPU machine.
3. **Proactive Assistance**: Detect user intent, confusion, or repetitive tasks and offer context-aware suggestions or automation.
4. **Agentic Automation**: Execute mouse/keyboard actions (PyAutoGUI) based on high-level goals, with a robust safety/confirmation layer.
5. **Persistent Memory**: Utilize a local vector database (ChromaDB) to remember user habits, past interactions, and specific project contexts.

## Non-Goals (Out of Scope)
- Building a custom LLM from scratch (will use existing local models).
- Full cross-platform support (Primary focus is Windows 10/11).
- Processing high-framerate video/gaming content (Vision is optimized for productivity/static apps).
- Remote cloud storage of user data (All memory stays local for privacy).

## Users
- Power users and developers who need an extra hand with complex workflows, troubleshooting, or repetitive tasks.
- Accessibility users who benefit from a voice-driven automation interface that "sees" the screen.

## Constraints
- **Hardware**: Must remain performant on 16GB RAM and integrated GPUs (Intel/AMD).
- **Latency**: Voice response and screen understanding must feel "real-time" (< 3-second round trip).
- **Privacy**: No screen data or personal interactions should leave the machine (except optional API fallback for complex reasoning).

## Success Criteria
- [ ] ay-eye successfully detects a terminal error and explains the fix via voice.
- [ ] ay-eye can automate a multi-step "New Project Setup" workflow (creating folders, running git init, opening IDE).
- [ ] System remains stable under 12GB total RAM usage during active ay-eye loop.
- [ ] Wake word ("Hey ay-eye") works reliably with 90%+ accuracy in a quiet room.
