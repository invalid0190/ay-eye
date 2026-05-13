# 👁️ Ay-Eye (ay-eye)

[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/invalid0190/ay-eye)

> [!WARNING]
> **Development Status**: This project is currently in the **Early Development Phase**. It is intended for experimental use and is **not yet production-ready**. Expect frequent breaking changes and bugs.

**Ay-Eye** is a powerful multimodal AI agent that acts as an autonomous extension of your desktop. Powered by **OpenAI GPT-4o** or **Anthropic Claude Sonnet 4.5** (toggleable), it "sees" your entire desktop, "hears" your voice commands, searches the web, and executes complex tasks—from browsing and messaging to creating code projects and navigating 3D software.

It is designed to act like a human-like, highly capable assistant living natively on your machine.

---

## 🌟 Why Choose Ay-Eye?

While tools like GitHub Copilot live in your IDE, and the ChatGPT Desktop app requires manual copy-pasting, **Ay-Eye bridges the gap between intelligence and autonomous action.**

1. **Total OS Control vs. Sandboxed APIs**: Unlike most AI tools that rely on specific API integrations, Ay-Eye "sees" your screen via computer vision and controls your actual mouse and keyboard. If a human can do it on a computer, Ay-Eye can do it too—no APIs required.
2. **True Multimodal Execution**: Ay-Eye doesn't just generate text. It can synthesize a web search, verbally explain the answer to you, and then autonomously type that answer into a Discord chat or a Word document.
3. **Multi-Monitor Native**: First-class support for spanning displays. Ay-Eye sees every connected monitor as a single labelled grid (`MON 1`, `MON 2`...) and can click between Discord on the left screen and VS Code on the right without losing track of which app lives where.
4. **UIA-First Clicking + Modern OCR**: Uses Windows UI Automation (semantic element trees) as the primary click strategy. Modern **RapidOCR** (ONNX) is the OCR fallback — 5-10× better small-text accuracy than Tesseract, especially on Discord channel names and badge counters.
5. **Developer-First "CMD" Capabilities**: Ay-Eye isn't just a UI clicker. It has a native terminal action pipeline. You can ask it to "Create a React project," and it will silently execute the proper PowerShell commands in the background.
6. **Dynamic Skill Learning**: Other agents are hardcoded. Ay-Eye features a dynamic *Skills System*. You can literally speak to it and say "Learn this workflow," and it will generate a JSON skill file and permanently inject that workflow into its brain for future use.
7. **No Cloud Vendor Lock-in**: While optimized for GPT-4o and Claude Sonnet 4.5, Ay-Eye supports graceful fallbacks (Moonshot/Kimi, AgentRouter, Ollama Cloud, local Ollama). You can run the entire vision and logic pipeline offline using Ollama if privacy is your absolute priority.

---

## ⚙️ How It Works (Under the Hood)

Ay-Eye operates on a high-speed continuous loop that combines real-time data ingestion with autonomous execution:

1. **Continuous Audio Stream**: The app listens for the `Alt + Z` hotkey globally. When pressed, a local `faster-whisper` model transcribes your voice in milliseconds.
2. **Context Compilation**:
   - **Vision**: `mss` captures the entire virtual desktop spanning every connected monitor. Each physical monitor's bounds are computed and labelled (`MON 1`, `MON 2`...) so the LLM can map "Discord on the left" to a concrete pixel range.
   - **UI Automation**: `UIAutoScanner` walks the accessibility tree of *every visible top-level window* (not just the foreground app), capturing semantic element names + automation IDs from up to 800 elements across all open apps.
   - **Knowledge**: If you asked a factual question, the `Web Search` module queries Brave Search.
   - **Memory**: The `SkillManager`, `RagManager`, and `ShortTermMemory` modules inject learned behaviours, app-specific rules, and past conversations.
   - **Cursor**: The current OS cursor position is mapped to image-space coordinates and passed to the LLM in a `CURSOR:` block so the model can plan moves from where the pointer actually is.
3. **Multimodal Reasoning**: All this context is packaged and sent to the LLM. **Structured outputs** (OpenAI strict JSON Schema or Anthropic forced tool-use) guarantee the response conforms to the action schema — no JSON healing needed for capable models.
4. **The Orchestrator**: The `ActionOrchestrator` decodes the structured response. 
   - If it needs to speak, it streams audio via **OpenAI TTS**.
   - If it needs to click, it tries **UIA** first (semantic match by name/automation-ID), falls back to **RapidOCR** locator, and only then to coordinate-based clicking. Movement uses `PyAutoGUI` with human-like easing curves.
   - If it needs to run a command, it bypasses the UI and pipes it directly into `subprocess/powershell`.
5. **Verification & Telemetry**: Per-turn token cost, prompt/completion sizes, and end-to-end latency are recorded by the telemetry module and surfaced live in the dashboard. Vision results are cached against perceptual hashes so unchanged screens don't re-spend tokens.

---

## 🚀 Core Features

- **👁️ Flawless Desktop Vision**: Uses `mss` for full-virtual-desktop capture and **GPT-4o** or **Claude Sonnet 4.5** Vision for deep pixel-perfect UI understanding. Captures span every connected monitor; per-monitor rectangles are drawn on the screenshot so the LLM never confuses left vs right display.
- **🧖 UIA-First Clicking with OCR Fallback**: `UIAutoScanner` enumerates every visible top-level window's accessibility tree (not just the foreground app) for instant, deterministic clicks by element name. **RapidOCR (ONNX)** kicks in only when UIA misses — dramatically more accurate than Tesseract on small Discord/Slack/Teams text.
- **🧠 Structured Outputs by Default**: OpenAI gpt-4o-family models use native strict JSON Schema; Anthropic Claude uses forced tool-use. The model is *guaranteed* to return well-formed action JSON, eliminating ~95% of JSON-parse retries.
- **📊 Per-Turn Telemetry + Vision Cache**: Live cost / token / latency / cache hit-rate displayed in the dashboard. Perceptual-hash-keyed vision cache skips re-OCR and re-LLM-vision on unchanged screens (~30% cost reduction on idle screens).
- **🧠 Advanced Memory System**: 
  - *Short-Term Memory*: Tracks full conversation context (your commands + its responses).
  - *Skill System*: Ay-Eye can dynamically learn new workflows and save them permanently to its brain (e.g. "Learn a skill called 'Daily Setup'").
- **💻 Developer / OS Control**: Can execute raw PowerShell commands natively, allowing you to say "Create a new React project" and watch it happen in the terminal.
- **🌍 Web-Augmented Intelligence**: Uses **Brave Search API** to fetch real-time information to answer knowledge questions before executing tasks.
- **🎙️ Voice Command & Control**: Hands-free interaction via `faster-whisper` for fast STT, and **OpenAI TTS** (Nova) for highly natural, responsive voice playback. 
- **🪟 Smart Window Management**: Utilizes the Win32 API to seamlessly switch between running windows or launch new apps via the Windows Registry.
- **🎯 Precise Automation**: Clicks, types, scrolls, and pastes using `pyautogui` and clipboard manipulation for speed and reliability.
- **💎 Premium UI**: Glassmorphism-inspired PyQt6 dashboard with floating cursor marker that spans all monitors, color-coded metrics, on-demand confirmation buttons, kbd-styled hotkey chips, and zero OS chrome.
- **💭 Plan Auto-Synthesis**: When the LLM forgets to include a `plan` field for low-risk multi-action turns, the validator synthesises one from the actions instead of silently dropping the user's task. High-risk operations (cmd, write_file, blender) still require explicit reasoning.
- **🧠 RAG Memory Layer**: Uses ChromaDB to store and retrieve app-specific rules, past failures, and project knowledge, helping the AI learn from its own mistakes.

---

## 💡 Use Cases & Capabilities

Because Ay-Eye is not restricted by APIs, its capabilities are limited only by its visual understanding. Here is what you can use it for:

- **Complex Software Navigation (e.g. Blender, Photoshop)**: "Switch to Blender, add a Torus mesh, and turn on proportional editing."
- **Autonomous Project Initialization**: "Create a new folder on my desktop called 'NextJS-App', initialize a NextJS project inside it, and open it in VS Code."
- **Data Gathering & Messaging**: "Search the web for the latest news on SpaceX, summarize the top 3 points, and send that summary to David on Discord."
- **Accessibility & Hands-Free Usage**: Navigate your entire computer, read emails, and dictate complex responses purely using your voice.
- **Automated QA / Testing**: Because it clicks native UI elements, you can train Ay-Eye to perform UI regression tests on your applications simply by talking to it.

---

## 🗺️ Roadmap & Recently Shipped

### ✅ Recently Shipped
- **Multi-Monitor Support**: All connected displays captured + labelled; per-monitor cursor + click coordinates surfaced to the LLM.
- **UIA-First Locator + RapidOCR**: Semantic UI Automation tries first; modern ONNX-based OCR replaces Tesseract as the primary fallback.
- **Structured Outputs**: Native JSON Schema (OpenAI gpt-4o family) and forced tool-use (Anthropic Claude) eliminate JSON-parse retries.
- **Anthropic Claude Backend**: Drop-in alternative to OpenAI — toggle via `LLM_PROVIDER=anthropic` in `.env`.
- **Per-Turn Telemetry + Vision Cache**: Live cost / latency dashboard; perceptual-hash cache skips redundant LLM/OCR calls.
- **Plan Auto-Synthesis**: Low-risk multi-action turns no longer silently fail when the LLM forgets the plan field.
- **Cursor Overlay Redesign**: Floating status pill + offset glow that spans every monitor and never occludes click targets.

### 🔬 In Progress / Planned
1. **Discord-Precision Retry Loop**: When `click_text` misses, locator crops the region, 2× upscales, and re-runs RapidOCR before giving up.
2. **Verification Loop Cost Cut**: Replace the second LLM verification call with screenshot-diff + OCR-confirm-target where possible (~40% cost reduction per task).
3. **Hybrid LLM Router**: Per-turn provider selection — fast turns to gpt-4o, tricky UI scenarios auto-retry with Claude.
4. **Local Codebase Integration**: Advanced file-system tools allowing Ay-Eye to act as a fully autonomous coding agent (read repo, write code, run tests).
5. **Always-On Wake Word**: Low-latency local wake word (e.g., "Hey Ay-Eye") to replace the `Alt + Z` hotkey.
6. **Contextual System Audio**: Routing desktop audio into the model's context for live meeting / video summarisation.
7. **Cross-App RPA**: Enhanced memory for complex multi-app data transfers (e.g., "Read my last email, summarize it, open Jira, and create a ticket").

---

### Tech Stack
- **Languages**: Python 3.13
- **Primary LLM & Vision**: OpenAI GPT-4o (strict JSON Schema) or Anthropic Claude Sonnet 4.5 (forced tool-use)
- **Alternative LLM Backends**: Moonshot/Kimi, AgentRouter (DeepSeek/GLM), Ollama Cloud, Local Ollama
- **OCR**: RapidOCR (ONNX) primary, Tesseract / Node fallback
- **UI Automation**: Windows UIA via `uiautomation` (semantic element trees)
- **Speech-to-Text (STT)**: Faster-Whisper (Local)
- **Text-to-Speech (TTS)**: OpenAI TTS (Fallback: Murf AI)
- **Web Search**: Brave Search API
- **UI**: PyQt6 (glassmorphism dashboard, multi-monitor cursor overlay)
- **Automation**: PyAutoGUI, Pyperclip, Win32 API (`ctypes`)
- **Memory**: ChromaDB (RAG); perceptual-hash vision cache; per-turn telemetry

---

## 📦 Installation & Setup

### Prerequisites
- **Python 3.13+**
- **Windows 10 / 11** (UIA + Win32 are Windows-only; multi-monitor support tested on dual-display setups)
- **Ollama locally installed** *(optional)* — only if you want a fully offline fallback.
- **Tesseract OCR** *(optional)* — RapidOCR (ONNX) is the new primary backend and is auto-installed via `requirements.txt`. Tesseract is only used as a secondary fallback. If you do install it, place it in PATH or `C:\Users\<YourUsername>\AppData\Local\Programs\Tesseract-OCR\`.

### 1. Configure Your AI Brain
Ay-Eye operates using a cascading fallback system. It attempts to use the best available engine configured in your `.env` file. Create a `.env` file in the root directory:

```env
# 🥇 PRIMARY OPTION A — OpenAI (default; native strict JSON Schema)
# Gives you GPT-4o Vision and ultra-fast OpenAI TTS.
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o

# 🥇 PRIMARY OPTION B — Anthropic Claude (forced tool-use structured output)
# Generally better at small UI elements (Discord channels, badges) and
# spatial reasoning across monitors. Slightly slower + slightly costlier.
# Set LLM_PROVIDER=anthropic to make this the active backend.
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5

# Active backend toggle. Priority when unset: openai > anthropic > moonshot > agentrouter > ollama.
# LLM_PROVIDER=openai          # default if both keys present
# LLM_PROVIDER=anthropic       # use Claude for everything
# LLM_PROVIDER=moonshot        # Kimi K2.6 (OpenAI-compatible)
# LLM_PROVIDER=agentrouter     # DeepSeek / GLM via AgentRouter
# LLM_PROVIDER=ollama          # hosted or local Ollama
LLM_PROVIDER=openai

# Optional: Kimi / Moonshot (OpenAI-compatible API)
MOONSHOT_API_KEY=your_moonshot_or_kimi_key_here
MOONSHOT_MODEL=kimi-k2.6
MOONSHOT_BASE_URL=https://api.moonshot.ai/v1

# 🥈 FALLBACK — Ollama Cloud + Murf AI
# Uses hosted Gemma 3 Vision and Murf AI TTS.
OLLAMA_API_KEY=your_ollama_cloud_key
MURF_API_KEY=your_murf_tts_key

# 🥉 FALLBACK — Local Offline (No keys needed)
# If no keys are provided, Ay-Eye will attempt to connect to http://localhost:11434
# You must have Ollama installed and the `gemma3:4b` model pulled.

# 🌐 WEB SEARCH (Required for knowledge queries)
BRAVE_API_KEY=your_brave_search_key_here
```

> [!CAUTION]
> **Never paste your `.env` contents into a chat, screenshot, GitHub issue, or commit.** API keys leak this way more often than from breaches. If you suspect a key has been exposed, rotate it immediately at the provider's console (OpenAI, Anthropic, Brave, etc.). `.env` is gitignored by default.

### 2. Install Dependencies
```bash
git clone https://github.com/invalid0190/ay-eye.git
cd ay-eye
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Running Offline / Local Ollama Setup
If you choose **not** to use OpenAI or Ollama Cloud, you must set up Ollama locally:
1. Download and install [Ollama](https://ollama.com/).
2. Open a terminal and pull the vision model:
   ```bash
   ollama run gemma3:4b
   ```
3. Keep Ollama running in the background.

### 4. Launch Ay-Eye
```bash
.venv\Scripts\python main.py
```

### 5. Ingest RAG Seed Rules
To initialize the memory with expert rules for apps like Blender and safety guidelines, run:
```bash
.venv\Scripts\python scripts/ingest_rag_seed.py
```

---

## 🧠 RAG (Retrieval-Augmented Generation)

Ay-Eye features a powerful **Long-Term Memory** layer using RAG (Retrieval-Augmented Generation) powered by **ChromaDB**. This allows the agent to learn from its mistakes and retain "expert knowledge" about specific applications like Blender.

### 🛠️ How It Works (Technical Overview)
- **Vector Database**: Uses **ChromaDB** to store high-dimensional embeddings of rules, skills, and past events.
- **Lazy Initialization**: The RAG layer is modular and initialized lazily, ensuring the app remains stable even if the database is unavailable.
- **Context Injection**: Before calling the LLM, the `RagManager` searches for context based on your current voice command, the active application, and the window title. Relevant memories are injected directly into the system prompt.

### 📚 Memory Collections
The memory is organized into specialized collections for high-precision retrieval:
1. **`ayeye_skills`**: Learned workflows and multi-step instructions.
2. **`ayeye_app_rules`**: Expert guidance for specific apps (e.g., "Blender uses OpenGL UI; avoid OCR clicking").
3. **`ayeye_past_failures`**: Automatic records of missed clicks, command errors, or OCR failures.
4. **`ayeye_project_knowledge`**: General information about your local files and project structures.
5. **`ayeye_user_preferences`**: Your specific habits and preferred ways of working.
6. **`ayeye_safety_rules`**: Guardrails against destructive commands or recursive UI loops.

### 🔄 Automatic Learning & Self-Correction
Ay-Eye is proactive. It doesn't just fail—it learns:
- **Click Failures**: If `click_text` fails to find a button, the executor records the failure and the app state. Next time you ask, the AI will see that memory and choose a more reliable method (like a coordinate click or keyboard shortcut).
- **Command Errors**: If a PowerShell command returns an error, it is stored as a `past_failure`. The AI will use this history to debug and fix its own commands in future attempts.
- **Success Summaries**: Successful complex sequences are summarized and stored to reinforce positive behavior.

### 🧪 Getting Started with Expert Rules
We provide a set of **Seed Rules** to jumpstart Ay-Eye's intelligence. These include critical safety guards and optimized Blender workflows.
To ingest the seed rules:
```bash
.venv\Scripts\python scripts/ingest_rag_seed.py
```

### ⚠️ The Source of Truth Rule
While RAG provides invaluable context, it is strictly **advisory**. 
- **RAG** = Memory & Experience (Guidance).
- **Live Perception** = Current Reality (Source of Truth).
Ay-Eye is hardcoded to prioritize what it currently **sees** on your screen over what it remembers from the past.

---

## 🧠 Model Selection: What's the Impact?

Because Ay-Eye controls your physical computer, the intelligence and speed of the underlying model dramatically impacts its performance.

| Feature | 🥇 OpenAI GPT-4o | 🥇 Anthropic Claude Sonnet 4.5 | 🥈 Ollama Cloud (Gemma 3) | 🥉 Local Ollama (Gemma 3) |
|---------|------------------|-------------------------------|---------------------------|---------------------------|
| **Vision Accuracy** | **Excellent**. Strong spatial understanding, rarely misses larger click targets. | **Best for small UI**. Reads tiny text (Discord channel names, badges) better than GPT-4o; better at multi-monitor spatial reasoning. | **Good**. Sometimes struggles with small UI elements or dense text. | **Good**. Same as cloud, but depends on your local GPU. |
| **Structured Output** | **Native strict JSON Schema** — model is *guaranteed* to return valid action JSON. | **Forced tool-use** — model emits a tool_use block whose input matches the brain schema. | **Fair**. Requires `JSONHealingParser` to fix formatting errors. | **Fair**. Requires healing parser. |
| **TTS Voice** | **OpenAI TTS (Nova)** — fastest, most expressive. | Uses OpenAI TTS (Anthropic doesn't ship a TTS API). | **Murf AI**. High quality, slower 2-step process. | **None** — Ay-Eye operates in text-only mode. |
| **Speed (per turn)** | ~600-1000 ms LLM + ~2-4 s end-to-end. | ~1000-1500 ms LLM + ~3-5 s end-to-end. | ~4-8 s depending on cloud load. | Depends entirely on your hardware (VRAM). |
| **Cost (per 1M tokens)** | $2.50 input / $10 output | $3 input / $15 output (~20-50% pricier) | Free (Ollama Cloud) | **Free** (your hardware). |
| **Privacy** | Data sent to OpenAI. | Data sent to Anthropic. | Data sent to Ollama Cloud. | **100% Private**. No screen data leaves your machine. |

**Verdict**:
- **General use, fastest + cheapest**: GPT-4o.
- **Best Discord / Slack / Teams precision, complex multi-step tasks**: Claude Sonnet 4.5 (`LLM_PROVIDER=anthropic`).
- **Maximum privacy / offline**: Local Ollama (Gemma 3).

You can keep both keys configured and toggle via `LLM_PROVIDER` without restarting your `.env` setup.

---

## 🚦 Controls
- **Hold Alt + Z**: Speak to Ay-Eye.
- **Alt + Enter**: Confirm a pending action (if confirmation is required).
- **Ctrl + Shift + X**: Emergency Stop (immediately halts all mouse/keyboard execution).

The dashboard shows the current state with a **floating cursor pill** (`AI` / `REC` / `THINKING` / `ACTING`) offset 14 px above the cursor on every monitor. The pill never sits on top of click targets, so you can always see exactly what the agent is doing without it occluding the UI.

---

## 🖥️ Multi-Monitor Support

Ay-Eye natively understands setups with two or more displays:

- **Capture spans the entire virtual desktop**, including monitors with negative coordinates (e.g. a secondary monitor placed to the *left* of the primary).
- **Adaptive resolution scaling** — a 3840×1080 dual-monitor capture is *not* down-sampled to 1920×540. The downscale cap is raised so per-monitor pixels remain legible for OCR and LLM vision.
- **Per-monitor labelling** — the screenshot drawn for the LLM has a thick cyan rectangle and `MON 1` / `MON 2` label inside each physical monitor's bounds.
- **Coordinate-aware prompt** — the LLM receives a `MONITORS:` block listing each monitor's image-x range and a `CURSOR:` block telling it exactly which monitor and pixel the OS pointer is on right now.
- **All-windows UIA scan** — `UIAutoScanner` walks the accessibility tree of *every visible top-level window*, not just the foreground app. So Ay-Eye can find Discord controls on the left monitor even while VS Code is active on the right.
- **Cursor overlay spans the union of all displays** — the floating status pill stays visible no matter which monitor you move the mouse to.

### Verifying Multi-Monitor Detection

After launching, check that all displays are detected:

```powershell
.venv\Scripts\python -c "import mss; sct = mss.mss(); print('Virtual:', sct.monitors[0]); [print(f'  Mon {i}:', m) for i, m in enumerate(sct.monitors[1:], 1)]"
```

Expected output for a dual-monitor setup:
```
Virtual: {'left': 0, 'top': 0, 'width': 3840, 'height': 1080}
  Mon 1: {'left': 0,    'top': 0, 'width': 1920, 'height': 1080}
  Mon 2: {'left': 1920, 'top': 0, 'width': 1920, 'height': 1080}
```

---

## 🔬 Debugging & Analytics

Because Ay-Eye relies on computer vision, seeing what the AI sees is critical for debugging. 
- **Vision Snapshots**: Every time the AI takes an action, it saves a compressed JPEG of the exact frame it analyzed to `analytics/vision_debug/`. You can view these images to ensure the AI's physical view of the screen matches yours.
- **Performance Logs**: Core operations (STT parsing, Vision latency, LLM reasoning) are logged in real-time to the terminal to help you monitor API performance and local latency.

---

## 🛡️ Pipeline Safety Tests

Ay-Eye includes a comprehensive test harness — **258 tests across 11 suites, all green** — that validates the full action pipeline **without** triggering real desktop interactions. No mouse clicks, keyboard input, or subprocess commands are executed.

### Quick Start

```bash
# Foundation infra
.venv\Scripts\python scripts/test_telemetry.py                # Per-turn cost / latency (22 tests)
.venv\Scripts\python scripts/test_vision_cache.py             # Perceptual-hash cache (25 tests)
.venv\Scripts\python scripts/test_dpi_coordinate_mapping.py   # DPI scaling (79 tests)

# Multi-monitor + UIA
.venv\Scripts\python scripts/test_multi_monitor.py            # Per-monitor layout (17 tests)
.venv\Scripts\python scripts/test_uia_first_locator.py        # UIA-first locator (14 tests)

# Pipeline / planning
.venv\Scripts\python scripts/test_response_schema.py          # LLM response validation
.venv\Scripts\python scripts/test_plan_validator.py           # Plan enforcement + auto-synthesis
.venv\Scripts\python scripts/test_agent_pipeline.py           # Full E2E pipeline (27 tests)
.venv\Scripts\python scripts/test_action_verifier.py          # Post-action verification (17 tests)
.venv\Scripts\python scripts/test_expect_contracts.py         # Expect contract evaluation (17 tests)

# LLM providers / structured outputs
.venv\Scripts\python scripts/test_response_format.py          # JSON Schema + Anthropic tool spec (27 tests)
.venv\Scripts\python scripts/test_anthropic_provider.py       # Claude provider dispatch + tool-use (26 tests)

# Real-world scenarios
.venv\Scripts\python scripts/test_real_world_scenarios.py     # 21 user-flow scenarios
.venv\Scripts\python scripts/test_rag_retrieval.py            # RAG retrieval quality
```

### What the Pipeline Tests Cover

| Test Group | What It Validates |
|------------|-------------------|
| Schema Validation | Malformed JSON, missing fields, invalid types, normalization |
| Plan Enforcement | Multi-action without plan, high-risk without plan, contradictions |
| Action Safety | Dangerous commands (`rm -rf`, `shutdown`, `format`), sensitive windows (banking, PayPal) |
| Confidence Gate | Low-confidence actions blocked before execution |
| Expect Contracts | File existence, command success, app focus, invalid contracts stripped |
| Mixed Actions | Valid actions survive alongside removed invalid actions |
| Guide/Ask Intents | Non-action responses pass through without execution |
| Complex Flows | Multi-step plans with cmd + write_file + click chains |

### Running Real-World Scenario Tests

Scenario tests simulate complete user workflows with realistic LLM responses:

```bash
.venv\Scripts\python scripts/test_real_world_scenarios.py    # 21 real-world scenarios
```

| Scenario | What It Tests |
|----------|---------------|
| Open Notepad + type | Launch app, type content, plan validation |
| Create project folder | cmd mkdir + write_file with expect contracts |
| Blender import | App switch + Blender API action with plan |
| Discord message | Click + type + hotkey chain with plan |
| Explain topic | Guide intent, no actions, high confidence |
| Block rm -rf / shutdown / diskpart / reg | Destructive commands caught by safety |
| Block bank / 1Password / PayPal typing | Sensitive window detection |
| Allow scroll in bank window | SAFE actions bypass sensitive window checks |
| click_text fallback | Recovery from OCR failure via short-term memory |
| Blender RAG rule | RAG-injected guidance applied correctly |
| Full project setup | 4-action flow with plan + 4 expect contracts |
| Low confidence | Blocked below threshold |
| Malformed response | Schema validation rejects non-dict actions |

### Live Dry-Run Mode

Ay-Eye includes a **Live Dry-Run Mode** that allows you to see what the agent *would* do without actually performing any clicks, typing, or command execution.

#### How to Enable

In `config.json`:
```json
{
  "dry_run_enabled": true,
  "dry_run_show_overlay": true
}
```

#### What happens in Dry-Run Mode:
1. **Full Validation**: The agent still runs Schema, Plan, and Safety validation.
2. **Visual Feedback**: A `DRY RUN` badge appears on the status bar.
3. **Action Preview**: UI action targets (like buttons) are highlighted on your real screen.
4. **Logging**: All intended actions are logged to the command panel and `ay-eye-analytics.jsonl`.
5. **Memory Update**: The agent's short-term memory is updated as if the action was attempted, allowing for multi-step reasoning tests.

> [!IMPORTANT]
> Always test new skills or complex workflows in **Dry-Run Mode** first to verify the agent's intent before allowing real execution.

#### Running Dry-Run Tests
To verify the dry-run plumbing itself:
```bash
.venv\Scripts\python scripts/test_dry_run_mode.py
```

### Reading Dry-Run Traces

When `dry_run_trace_enabled` is true, every simulated sequence generates a JSON trace in `data/traces/`. This is the ultimate debugging tool for understanding the agent's internal state.

**Trace Structure:**
- `timestamp`: When the sequence occurred.
- `user_command`: The original request (from short-term memory).
- `llm_response`: The raw (truncated) JSON from the LLM.
- `schema_result`: Whether the JSON was valid and what was normalized.
- `plan_result`: If the plan was accepted or why it was rejected.
- `safety_results`: A per-action risk assessment (SAFE/LOW/MEDIUM/HIGH/BLOCKED).
- `final_status`: `simulated` (success), `blocked` (safety refusal), or `failed` (validation error).

**Why use traces?**
- **Debug Refusals**: See exactly which safety rule or sensitive window triggered a block.
- **Audit Logic**: Verify that the agent is creating a plan for high-risk actions.
- **Improve Prompts**: Analyze `schema_result` to see if the LLM is consistently outputting invalid JSON.

### Pipeline Architecture

```
                      ┌─────────────────────────┐
                      │  Voice / Typed Command  │
                      └────────────┬────────────┘
                                   v
                      ┌─────────────────────────┐
                      │  Brain — Context Build   │
                      │  • Vision + monitor map  │
                      │  • UIA tree (all windows)│
                      │  • RAG + skills + memory │
                      │  • Cursor pos + state    │
                      └────────────┬────────────┘
                                   v
                      ┌─────────────────────────┐
                      │  LLM Bridge              │
                      │  • Strict JSON Schema    │  ← OpenAI gpt-4o
                      │  • Forced tool-use       │  ← Anthropic Claude
                      │  • Healing fallback      │  ← Others
                      └────────────┬────────────┘
                                   v
                      ┌─────────────────────────┐
                      │  Telemetry Recorder      │
                      │  Tokens / cost / ms      │ → Dashboard
                      └────────────┬────────────┘
                                   v
                  1. Schema Validator    — normalize, strip invalid actions
                                   |
                                   v
                  2. Plan Validator      — auto-synthesise plan if low-risk
                                   |    — require explicit plan for cmd/write_file
                                   v
                  3. Action Safety       — block destructive cmds, sensitive windows
                                   |
                                   v
                  4. Confirmation Gate   — pause for Alt+Enter on high-risk
                                   |
                                   v
                  5. Executor            — UIA → RapidOCR → coordinate clicks
                                   |    — PyAutoGUI / PowerShell
                                   v
                  6. Action Verifier     — expect contract or screen diff
                                   v
                      ┌─────────────────────────┐
                      │  RAG / Memory Update     │
                      │  Successes + failures    │
                      └─────────────────────────┘
```

---

## 📄 License
MIT License - see the [LICENSE](LICENSE) file for details.
