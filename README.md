# 👁️ Ay-Eye (ay-eye)

[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/invalid0190/ay-eye)

> [!WARNING]
> **Development Status**: This project is currently in the **Early Development Phase**. It is intended for experimental use and is **not yet production-ready**. Expect frequent breaking changes and bugs.

**Ay-Eye** is a powerful multimodal AI agent that acts as an autonomous extension of your desktop. By combining **real-time computer vision**, voice recognition, and **Gemma 3 Vision** models, Ay-Eye "sees" your entire desktop and "hears" your commands, executing complex tasks with pixel-perfect accuracy.

---

## 🚀 Core Features

- **👁️ Desktop Vision**: Uses `mss` for full-desktop capture (multi-monitor support) and `Gemma 3` for visual understanding.
- **🎙️ Voice Command & Control**: Hands-free interaction via `faster-whisper`. Hold `Alt + Z` to speak.
- **🎯 Precise Automation**: Click, Type, Scroll, and Launch apps using human-like mouse movements and easing curves.
- **💎 Premium UI**: A glassmorphism-inspired dashboard with real-time status indicators, activity logs, and chat history.
- **🛡️ Safety First**: Integrated "Safe Zone" clamping and `Ctrl+Shift+X` emergency stop to ensure your system is always under control.
- **🌍 Hybrid Cloud-Local**: High-speed STT runs locally, while LLM (Ollama Cloud) and TTS (Murf AI) leverage professional cloud pipelines.

---

## 🛠️ Architecture

### The Vision Loop
1.  **Capture**: Captures the entire virtual desktop (all monitors).
2.  **Perception**: Resizes and encodes the screen for the Vision LLM (Gemma 3).
3.  **Brain**: The LLM analyzes the screenshot and the user command, returning structured JSON with pixel coordinates.
4.  **Execution**: `PyAutoGUI` translates those coordinates into smooth, human-like mouse and keyboard actions.

### Tech Stack
- **Languages**: Python 3.13
- **Vision LLM**: Ollama Cloud (Gemma 3 Vision)
- **STT**: Faster-Whisper (Local)
- **TTS**: Murf AI (Natalie voice)
- **UI**: PyQt6 (Glassmorphism)

---

## 📦 Installation & Setup

### Prerequisites
- **Python 3.13+**
- **Ollama Cloud API Key**
- **Murf AI API Key**

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
   Create a `.env` file:
   ```env
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
- **Alt + Enter**: Confirm a pending action.
- **Ctrl + Shift + X**: Emergency Stop.

---

## 📄 License
MIT License - see the [LICENSE](LICENSE) file for details.
