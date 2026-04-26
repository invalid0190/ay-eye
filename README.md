# 👁️ Ay-Eye (ay-eye)

[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/invalid0190/ay-eye)

> [!WARNING]
> **Development Status**: This project is currently in the **Early Development Phase**. It is intended for experimental use and is **not yet production-ready**. Expect frequent breaking changes and bugs.

**Ay-Eye** is a powerful multimodal AI agent that acts as an autonomous extension of your desktop. Powered by **OpenAI GPT-4o**, it "sees" your entire desktop, "hears" your voice commands, searches the web, and executes complex tasks—from browsing and messaging to creating code projects and navigating 3D software.

It is designed to act like a human-like, highly capable assistant living natively on your machine.

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

## 🛠️ Architecture

### The Vision & Action Loop
1. **Trigger**: User holds `Alt + Z` to speak. Local `faster-whisper` transcribes audio instantly.
2. **Context Gathering**: Captures the screen, fetches web results (if needed), loads recent conversation history, and loads learned *Skills*.
3. **Reasoning**: GPT-4o analyzes the multimodal prompt and outputs a structured JSON action plan.
4. **Execution**: The Action Orchestrator parses the JSON and executes actions: `click`, `type`, `hotkey`, `launch`, `switch`, `cmd`, or `create_skill`.

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
