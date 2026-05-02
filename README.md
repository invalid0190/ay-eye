# 👁️ Ay-Eye (ay-eye)

[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/invalid0190/ay-eye)

> [!WARNING]
> **Development Status**: This project is currently in the **Early Development Phase**. It is intended for experimental use and is **not yet production-ready**. Expect frequent breaking changes and bugs.

**Ay-Eye** is a powerful multimodal AI agent that acts as an autonomous extension of your desktop. Powered by **OpenAI GPT-4o**, it "sees" your entire desktop, "hears" your voice commands, searches the web, and executes complex tasks—from browsing and messaging to creating code projects and navigating 3D software.

It is designed to act like a human-like, highly capable assistant living natively on your machine.

---

## 🌟 Why Choose Ay-Eye?

While tools like GitHub Copilot live in your IDE, and the ChatGPT Desktop app requires manual copy-pasting, **Ay-Eye bridges the gap between intelligence and autonomous action.**

1. **Total OS Control vs. Sandboxed APIs**: Unlike most AI tools that rely on specific API integrations, Ay-Eye "sees" your screen via computer vision and controls your actual mouse and keyboard. If a human can do it on a computer, Ay-Eye can do it too—no APIs required.
2. **True Multimodal Execution**: Ay-Eye doesn't just generate text. It can synthesize a web search, verbally explain the answer to you, and then autonomously type that answer into a Discord chat or a Word document.
3. **Developer-First "CMD" Capabilities**: Ay-Eye isn't just a UI clicker. It has a native terminal action pipeline. You can ask it to "Create a React project," and it will silently execute the proper PowerShell commands in the background.
4. **Dynamic Skill Learning**: Other agents are hardcoded. Ay-Eye features a dynamic *Skills System*. You can literally speak to it and say "Learn this workflow," and it will generate a JSON skill file and permanently inject that workflow into its brain for future use.
5. **No Cloud Vendor Lock-in**: While optimized for GPT-4o, Ay-Eye supports graceful fallbacks. You can run the entire vision and logic pipeline offline using Ollama if privacy is your absolute priority.

---

## ⚙️ How It Works (Under the Hood)

Ay-Eye operates on a high-speed continuous loop that combines real-time data ingestion with autonomous execution:

1. **Continuous Audio Stream**: The app listens for the `Alt + Z` hotkey globally. When pressed, a local `faster-whisper` model transcribes your voice in milliseconds.
2. **Context Compilation**:
   - **Vision**: `mss` captures a raw frame of your entire virtual desktop (all monitors).
   - **Knowledge**: If you asked a factual question, the `Web Search` module queries Brave Search.
   - **Memory**: The `SkillManager` and `ShortTermMemory` modules inject past conversations and learned behaviors.
3. **Multimodal Reasoning**: All this context is packaged and sent to the LLM (GPT-4o). The AI acts as a decision engine, outputting a strict JSON format dictating exactly what must happen next.
4. **The Orchestrator**: The `ActionOrchestrator` decodes the JSON. 
   - If it needs to speak, it streams audio via **OpenAI TTS**.
   - If it needs to click/type, it calculates coordinates and uses `PyAutoGUI` with human-like easing curves.
   - If it needs to run a command, it bypasses the UI and pipes it directly into `subprocess/powershell`.

---

## 🚀 Core Features

- **👁️ Flawless Desktop Vision**: Uses `mss` for full-desktop capture and **GPT-4o Vision** for deep pixel-perfect understanding of UIs.
- **🧠 Advanced Memory System**: 
  - *Short-Term Memory*: Tracks full conversation context (your commands + its responses).
  - *Skill System*: Ay-Eye can dynamically learn new workflows and save them permanently to its brain (e.g. "Learn a skill called 'Daily Setup'").
- **💻 Developer / OS Control**: Can execute raw PowerShell commands natively, allowing you to say "Create a new React project" and watch it happen in the terminal.
- **🌍 Web-Augmented Intelligence**: Uses **Brave Search API** to fetch real-time information to answer knowledge questions before executing tasks.
- **🎙️ Voice Command & Control**: Hands-free interaction via `faster-whisper` for fast STT, and **OpenAI TTS** (Nova) for highly natural, responsive voice playback. 
- **🪟 Smart Window Management**: Utilizes the Win32 API to seamlessly switch between running windows or launch new apps via the Windows Registry.
- **🎯 Precise Automation**: Clicks, types, scrolls, and pastes using `pyautogui` and clipboard manipulation for speed and reliability.
- **💎 Premium UI**: A glassmorphism-inspired PyQt6 dashboard with real-time status indicators, activity logs, and system health checks.
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

## 🗺️ Roadmap & Future Capabilities

To ensure Ay-Eye remains a cutting-edge autonomous agent, the following features are actively being explored:

1. **Agentic Verification Loop**: Moving from single-shot execution to continuous autonomous loops. Ay-Eye will take verification screenshots after every action to confirm success or self-correct if an app is lagging.
2. **Local Codebase Integration**: Advanced file-system reading tools allowing Ay-Eye to act as a fully autonomous coding agent (similar to Devin) that can read your repository, write code, and run tests.
3. **Always-On Wake Word**: Replacing the `Alt + Z` hotkey with a low-latency local wake word (e.g., "Hey Ay-Eye") for truly hands-free operation.
4. **Contextual System Audio**: Routing desktop audio into the model's context so it can summarize live meetings, YouTube videos, or podcasts in real-time.
5. **Cross-App RPA**: Enhanced memory allowing complex multi-app data transfers (e.g., "Read my last email, summarize it, open Jira, and create a ticket").

---

### Tech Stack
- **Languages**: Python 3.13
- **Primary LLM & Vision**: OpenAI GPT-4o
- **Fallback LLM**: Ollama Cloud / Local Ollama
- **Speech-to-Text (STT)**: Faster-Whisper (Local)
- **Text-to-Speech (TTS)**: OpenAI TTS (Fallback: Murf AI)
- **Web Search**: Brave Search API
- **UI**: PyQt6
- **Automation**: PyAutoGUI, Pyperclip, Win32 API (`ctypes`)

---

## 📦 Installation & Setup

### Prerequisites
- **Python 3.13+**
- **Ollama locally installed** (If you want to run offline)
- **Tesseract OCR installed on Windows** (Required for the `click_text` feature. Ensure it's installed either in your PATH or inside your user folder: `C:\Users\<YourUsername>\AppData\Local\Programs\Tesseract-OCR\`)

### 1. Configure Your AI Brain
Ay-Eye operates using a cascading fallback system. It attempts to use the best available engine configured in your `.env` file. Create a `.env` file in the root directory:

```env
# 🥇 PRIMARY: OpenAI (Highly Recommended)
# Gives you GPT-4o Vision and ultra-fast OpenAI TTS.
OPENAI_API_KEY=your_openai_api_key_here

# 🥈 FALLBACK 1: Ollama Cloud + Murf AI
# Uses hosted Gemma 3 Vision and Murf AI TTS.
OLLAMA_API_KEY=your_ollama_cloud_key
MURF_API_KEY=your_murf_tts_key

# 🥉 FALLBACK 2: Local Offline (No keys needed)
# If no keys are provided, Ay-Eye will attempt to connect to http://localhost:11434
# You must have Ollama installed and the `gemma3:4b` model pulled.

# 🌐 WEB SEARCH (Required for knowledge queries)
BRAVE_API_KEY=your_brave_search_key_here
```

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

| Feature | 🥇 OpenAI (GPT-4o) | 🥈 Ollama Cloud (Gemma 3) | 🥉 Local Ollama (Gemma 3) |
|---------|--------------------|---------------------------|---------------------------|
| **Vision Accuracy** | **Flawless**. GPT-4o has a deep understanding of spatial coordinates and rarely misses a click target. | **Good**. Sometimes struggles with small UI elements or dense text areas. | **Good**. Same as cloud, but depends on your local GPU. |
| **JSON Reliability** | **Perfect**. Uses native `json_object` format. | **Fair**. Requires our custom `JSONHealingParser` to fix formatting errors. | **Fair**. Requires healing parser. |
| **TTS Voice** | **OpenAI TTS (Nova)**. Extremely fast (streams directly as MP3) and highly expressive. | **Murf AI**. High quality, but slower due to a 2-step generate/download process. | **None**. Ay-Eye will operate silently in text-only mode. |
| **Speed** | Takes ~2-4 seconds to perceive, think, and start acting. | Takes ~4-8 seconds depending on cloud load. | Depends entirely on your hardware (VRAM). |
| **Privacy** | Data sent to OpenAI. | Data sent to Ollama Cloud. | **100% Private**. No screen data leaves your machine. |

**Verdict**: If you want the agent to be a highly capable, autonomous developer assistant, **use OpenAI**. If you are doing basic OS navigation and value extreme privacy, **use Local Ollama**.

---

## 🚦 Controls
- **Hold Alt + Z**: Speak to Ay-Eye.
- **Alt + Enter**: Confirm a pending action (if confirmation is required).
- **Ctrl + Shift + X**: Emergency Stop (immediately halts all mouse/keyboard execution).

---

## 🔬 Debugging & Analytics

Because Ay-Eye relies on computer vision, seeing what the AI sees is critical for debugging. 
- **Vision Snapshots**: Every time the AI takes an action, it saves a compressed JPEG of the exact frame it analyzed to `analytics/vision_debug/`. You can view these images to ensure the AI's physical view of the screen matches yours.
- **Performance Logs**: Core operations (STT parsing, Vision latency, LLM reasoning) are logged in real-time to the terminal to help you monitor API performance and local latency.

---

## 🛡️ Pipeline Safety Tests

Ay-Eye includes a comprehensive test harness that validates the full action pipeline **without** triggering real desktop interactions. No mouse clicks, keyboard input, or subprocess commands are executed.

### Quick Start

```bash
# Run the full end-to-end pipeline test (27 test cases)
.venv\Scripts\python scripts/test_agent_pipeline.py

# Run individual component tests
.venv\Scripts\python scripts/test_response_schema.py    # LLM response validation (30 tests)
.venv\Scripts\python scripts/test_plan_validator.py      # Plan enforcement (20 tests)
.venv\Scripts\python scripts/test_action_verifier.py     # Post-action verification (17 tests)
.venv\Scripts\python scripts/test_expect_contracts.py    # Expect contract evaluation (17 tests)
.venv\Scripts\python scripts/test_rag_retrieval.py       # RAG retrieval quality
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

### Pipeline Architecture

```
LLM Response
    |
    v
1. Schema Validator      -- Normalize/sanitize, strip invalid actions
    |
    v
2. Plan Validator        -- Require plan for 3+ actions or high-risk
    |
    v
3. Action Safety         -- Block dangerous commands, sensitive windows
    |
    v
4. Executor              -- Run the action (mouse/keyboard/cmd)
    |
    v
5. Action Verifier       -- Check expect contract or screen-change heuristic
```

---

## 📄 License
MIT License - see the [LICENSE](LICENSE) file for details.

