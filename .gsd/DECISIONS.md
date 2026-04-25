# DECISIONS.md

## Phase 1: Foundation & Vision — Decisions

**Date:** 2026-04-25

### Architecture & Strategy
- **Capture Strategy:** Active window ONLY.
- **Monitor Strategy:** Follow cursor monitor (one at a time).
- **Hybrid UI Detection:** Primary `UIAutomation` (via `comtypes`) for structure; secondary `pytesseract` for visual text.
- **Loop Design:** Multi-threaded (Capture, Processing, Context, AI Trigger).

### Implementation Details
- **OCR Engine:** `pytesseract` (Phase 1 will include Tesseract binary installation instructions).
- **Optimization:** 
  - Frame diffing/hashing to skip processing of static screens.
  - Region-based OCR (focused on text areas).
  - OpenCV preprocessing (grayscale + thresholding).
- **AI Triggers:** AI is only called on "Smart Triggers" (New UI, Error detected, User idle 5-10s, Repeat actions).

### Privacy & Safety
- **Blacklist System:** Mandatory pausing for browsers (incognito), password managers, and banking apps.
- **State Object:** Centralized `CurrentState` singleton for inter-module communication.

---

## Phase 2: The Brain & Memory — Decisions

**Date:** 2026-04-25

### Intelligence & Reasoning
- **Model:** Local Ollama (Llama 3 8B / Mistral 7B) with cloud API fallback.
- **JSON Reliability:** Hybrid system using strict prompting + a lightweight custom "healing parser" (extract blocks, fix quotes/commas, validate schema). No heavy frameworks.
- **Prompt Structure:** 3-layer (System, Context, Task) to keep instructions clear and modular.

### Memory & Context
- **Memory Retrieval:** Hybrid system: 1. Filter by Context (App/Window) → 2. Rank by Semantic Similarity (Goal/Frustration patterns).
- **Storage:** Disk-persistent ChromaDB with minimal RAM footprint. Retrieval limited to top 3-5 results and strict token caps.
- **Context Distillation:** Rule-based filtering (Prioritize: Errors, Buttons, Inputs, Titles) with smart truncation. No heavy summarizer module.

### Execution Control
- **Gating System:** AI calls only if: 1. Trigger Confidence > 0.7, 2. Outside cooldown (5-10s), 3. Context is meaningful (not passive reading).
- **Response Modes:** Post-processing determines mode based on confidence:
  - < 0.5: Silent (Ignore)
  - 0.5 - 0.7: UI Suggestion only
  - > 0.7: Voice + UI Suggestion
- **Failure Handling:** Single retry on JSON failure; fallback to "Safe Response" (clarification request).

---

## Phase 3: Voice & Communication — Decisions

**Date:** 2026-04-25

### Voice Capture (STT)
- **Engine:** `faster-whisper` (optimized CTranslate2) for low-latency local inference.
- **Activation:** `Alt + Z` (Push-to-Talk). No continuous heavy listening to save CPU.
- **Buffering:** Silence detection (0.5-0.7s) to trigger transcription; 10s maximum recording window as a fail-safe.
- **Event:** Emits `VOICE_INPUT_RECEIVED` containing the transcribed text.

### Voice Synthesis (TTS)
- **Engine:** `pyttsx3` (lightweight system voices).
- **Identity:** System default voice with 1.1x - 1.2x speech rate for efficiency.
- **Interrupt System:** Immediate TTS stop on any **Keypress** or **Mouse Click**. (Mouse movement does not stop speech).

### Control Logic
- **Gating:** Voice is only triggered if:
  1. Confidence > 0.7.
  2. Mode allows voice.
  3. Not within speech cooldown window.
- **Event:** Subscribes to `BRAIN_RESPONDED` and processes the "message" field for speech.
- **Safety:** Immediate release of audio resources after each interaction.

---

## Phase 4: Automation & Control — Decisions

**Date:** 2026-04-25

### Action Execution
- **Core Engine:** `pyautogui` for low-level mouse and keyboard control.
- **Phased Autonomy:** 
  - **Level 1:** Always confirm (initial 5-10 uses).
  - **Level 2:** Adaptive trust (auto-execute safe/known tasks).
  - **Level 3:** Full automation (future).
- **Sequential Steps:** Actions are executed one-by-one with 100-300ms delays and post-action UI verification.

### Safety & Visuals
- **Kill Switch:** `Ctrl + Shift + X` for a hard stop (immediate termination of action thread).
- **Visual Feedback:** PyQt6 transparent overlay draws a bounding box over the target for 150-250ms before clicking.
- **Targeting:** Priority order: 1. UIAutomation element matching → 2. OCR text-based bounding boxes → 3. Disambiguation request (if >1 match).
- **Whitelisting:** `OPEN_APP` actions only permitted for a predefined list of "Safe Apps."

### Trust & Logic
- **Trust Model:** Trust scores are tracked per action type (`click`, `type`, `open_app`). Fails or user cancellations reset trust.
- **Validation:** Minimum confidence of 0.8 required for any automated action.
- **Ambiguity:** Zero-guessing policy. If multiple targets exist in the active window, stop and ask the user via voice.
