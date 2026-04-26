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
- **OpenAI API Key** (Highly Recommended for primary functionality)
- **Brave Search API Key** (For web capabilities)
- *(Optional)* Ollama Cloud / Murf AI Keys (For fallbacks)

### Setup
1. **Clone & Install:**
   ```bash
   git clone https://github.com/invalid0190/ay-eye.git
   cd ay-eye
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment:**
   Create a `.env` file in the root directory:
   ```env
   # Primary AI Engine (Vision, Reasoning, TTS)
   OPENAI_API_KEY=your_openai_api_key_here
   
   # Web Search
   BRAVE_API_KEY=your_brave_search_key_here

   # Fallbacks (Optional)
   MURF_API_KEY=your_murf_api_key_here
   OLLAMA_API_KEY=your_ollama_api_key_here
   ```

3. **Run:**
   ```bash
   .venv\Scripts\python main.py
   ```

---

## 🚦 Controls
- **Hold Alt + Z**: Speak to Ay-Eye.
- **Alt + Enter**: Confirm a pending action (if confirmation is required).
- **Ctrl + Shift + X**: Emergency Stop (immediately halts all mouse/keyboard execution).

---

## 📄 License
MIT License - see the [LICENSE](LICENSE) file for details.
