# 👁️ Ay-Eye (ay-eye)

[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/invalid0190/ay-eye)

> [!WARNING]
> **Development Status**: This project is currently in the **Early Development Phase**. It is intended for experimental use and is **not yet production-ready**. Expect frequent breaking changes and bugs.

**Ay-Eye** is an autonomous, multimodal AI agent designed to act as a seamless extension of your digital workspace. By combining real-time computer vision, voice recognition, and local large language models, Ay-Eye "sees" what you see and "hears" what you say, providing intelligent assistance without ever leaving your local machine.

Inspired by next-generation agentic frameworks like OpenDevin and OpenClaude, Ay-Eye prioritizes **privacy, speed, and deep system integration**.

---

## 🚀 Core Features

- **Multimodal Perception**: Real-time screen capture and OCR analysis using a distributed Node.js/Python bridge.
- **Voice-Driven Command & Control**: Hands-free interaction via high-performance local STT (Faster-Whisper).
- **Privacy-First Intelligence**: Fully local LLM orchestration powered by Ollama (Llama 3/3.2).
- **Dynamic Visual Overlay**: A glassmorphism-inspired UI that provides real-time "AI Cursor" tracking and status feedback.
- **Event-Driven Architecture**: A robust internal event bus for seamless coordination between vision, voice, and decision engines.

---

## 🛠️ Architecture & Workflow

Ay-Eye is built on a hybrid stack designed for maximum reliability and local performance. Unlike traditional agents that rely on cloud APIs, Ay-Eye orchestrates multiple local engines in parallel:

### The Intelligence Loop
1.  **Perception (Vision/Voice)**: 
    - **Vision**: Captures the active window every 500ms, performing change detection and background OCR via a specialized Node.js worker using `tesseract.js` (WebAssembly).
    - **Voice**: Listens for the `Alt + Z` hotkey to capture high-fidelity audio, which is then transcribed using `faster-whisper`.
2.  **State Management**: 
    - All perceived data is piped into a central **System State** manager that maintains a real-time "Snapshot" of your current workspace.
3.  **The Brain (Ollama)**: 
    - When a trigger (Idle, Voice, or Error) occurs, the **Context Distiller** prepares a minimized prompt for Ollama (`llama3`).
    - The LLM processes the current state and returns a structured JSON response.
4.  **Action Orchestration**: 
    - Based on the Brain's decision, the system either speaks to the user (TTS), highlights elements on the screen, or prepares an automated UI action.

### Tech Stack
- **Languages**: Python 3.13 (Core), JavaScript/Node.js (OCR Engine).
- **Inference**: Ollama (LLM), Faster-Whisper (STT).
- **UI Framework**: PyQt6 with custom glassmorphism styling.
- **Inter-process Communication**: Internal Event Bus (Pub/Sub pattern).

---

## 🗺️ Roadmap & Upcoming Features

- [ ] **Multimodal Vision-LLM Support**: Integration with `llava` for deeper visual understanding beyond OCR.
- [ ] **Plugin System**: Allow users to add custom "Skills" (e.g., Browser automation, File system management).
- [ ] **Improved Latency**: Persistent Node.js worker processes and socket-based communication.
- [ ] **Context Window Optimization**: RAG (Retrieval-Augmented Generation) for long-term project memory.
- [ ] **Cross-Platform Support**: Full support for macOS and Linux (Wayland/X11).

---

## 🤝 Contributing

We welcome contributions! Whether you're fixing a bug, adding a feature, or improving documentation:

1. Fork the Project.
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the Branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

---

## 📦 Installation

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** (for OCR engine)
- **Ollama** (running locally with `llama3` pulled)

### Setup
1. **Clone the repository:**
   ```bash
   git clone https://github.com/invalid0190/ay-eye.git
   cd ay-eye
   ```

2. **Setup Python Environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

3. **Setup OCR Engine:**
   ```bash
   cd core/ocr/node_engine
   npm install
   cd ../../../
   ```

---

## 🚦 Usage

1. Start the Ay-Eye engine:
   ```bash
   .venv\Scripts\python main.py
   ```

2. **Interacting with Ay-Eye:**
   - **Alt + Z**: Hold to record a voice command.
   - **Alt + Enter**: Confirm a suggested action.
   - **Ctrl + Shift + X**: Emergency stop.

---

## 🛡️ Privacy Commitment
Ay-Eye is designed to be **Zero-Data-Exfiltration**. All screen captures, audio segments, and LLM inferences are processed entirely on your local hardware. No data ever leaves your system unless you explicitly configure an external provider.

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
