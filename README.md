# 👁️ Ay-Eye (ay-eye)

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

## 🛠️ Architecture

Ay-Eye is built on a hybrid stack designed for maximum reliability and local performance:

- **Brain**: Orchestration layer using local LLMs (Ollama).
- **Vision**: Real-time screen capture with specialized OCR processing (Tesseract.js).
- **Voice**: Low-latency STT processing using Faster-Whisper.
- **UI**: High-performance PyQt6 overlay with hardware-accelerated rendering.

---

## 📦 Installation

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** (for OCR engine)
- **Ollama** (running locally with `llama3` pulled)

### Setup
1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/ay-eye.git
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
