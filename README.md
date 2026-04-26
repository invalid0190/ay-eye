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

## 📄 License
MIT License - see the [LICENSE](LICENSE) file for details.
