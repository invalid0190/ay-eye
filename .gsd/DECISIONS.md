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
