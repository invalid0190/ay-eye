# ay-eye Setup Instructions (Phase 1)

## Prerequisites

### 1. Python 3.10+
Ensure Python is installed and added to your PATH.

### 2. Tesseract-OCR (Required for Vision)
1. Download the installer from [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
2. Install it (default path is usually `C:\Program Files\Tesseract-OCR`).
3. Add `C:\Program Files\Tesseract-OCR` to your System **PATH** environment variable.
4. Verify by running `tesseract --version` in a terminal.

### 3. Dependencies
Run the following command in the project root:
```bash
pip install pydantic pygetwindow pyautogui mss pytesseract opencv-python comtypes imagehash
```

## Running the Assistant
To start the core vision loop:
```bash
python main.py
```

## Project Structure
- `/core`: Main logic modules
  - `/engine`: Event Bus and Orchestration
  - `/vision`: Screen capture and window management
  - `/ocr`: Text extraction
  - `/ui`: Windows UIAutomation interface
  - `/state`: Thread-safe project memory
  - `/utils`: Logging and helpers
- `main.py`: Entry point
