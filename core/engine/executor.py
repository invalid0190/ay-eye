import os
import pyautogui
import subprocess
import time
import random
import threading
from core.engine.event_bus import bus
from core.engine.action_state import action_state
from core.engine.window_manager import window_manager
from core.utils.logger import logger

class ActionExecutor:
    def __init__(self):
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        self._stop_event = threading.Event()
        bus.subscribe("EMERGENCY_STOP", self.stop)
        
        # Get screen size for clamping
        self.screen_w, self.screen_h = pyautogui.size()

    def stop(self, data=None):
        self._stop_event.set()
        action_state.stop_action()
        logger.log_event("EXECUTOR_FORCE_STOPPED")

    def execute_sequence(self, actions):
        self._stop_event.clear()
        for action in actions:
            if self._stop_event.is_set():
                break
            # Increased delay to allow UI elements (like context menus) to render
            time.sleep(random.uniform(0.5, 0.8))
            self.execute_single(action)

    def execute_single(self, action):
        if self._stop_event.is_set():
            return

        a_type = action.get("type")
        bus.publish("ACTION_STARTED", action)
        logger.log_event("ACTION_STARTED", action)
        
        try:
            if a_type == "click":
                x = action.get("x")
                y = action.get("y")
                button = action.get("button", "left")  # left, right, middle
                clicks = action.get("clicks", 1)        # 1 = single, 2 = double
                
                if x is not None and y is not None:
                    jx = max(10, min(self.screen_w - 10, x + random.randint(-2, 2)))
                    jy = max(10, min(self.screen_h - 10, y + random.randint(-2, 2)))
                    
                    duration = random.uniform(0.3, 0.5)
                    pyautogui.moveTo(jx, jy, duration=duration, tween=pyautogui.easeOutQuad)
                    time.sleep(random.uniform(0.05, 0.15))
                    pyautogui.click(button=button, clicks=clicks)
                    logger.logger.info(f"Executor: {button}-click x{clicks} at ({jx},{jy})")
                    
                    # Inject click feedback into memory for AI self-correction
                    target_name = action.get("target", "unknown element")
                    from core.state.short_term import short_term_memory
                    short_term_memory.add_system_context(
                        f"CLICK_EXECUTED: {button}-click x{clicks} at pixel ({jx},{jy}) targeting '{target_name}'"
                    )
                else:
                    logger.logger.warning(f"Click action missing coordinates: {action}")
                    
            elif a_type == "click_text":
                text_to_find = action.get("text", "")
                button = action.get("button", "left")
                clicks = action.get("clicks", 1)
                
                if text_to_find:
                    import mss
                    from PIL import Image
                    import pytesseract
                    from pytesseract import Output
                    
                    found = False
                    with mss.mss() as sct:
                        # Use monitor[1] (primary) not monitor[0] (virtual desktop)
                        # monitor[0] can have negative offsets on multi-monitor setups
                        monitor = sct.monitors[1]
                        screenshot = sct.grab(monitor)
                        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                        
                        # Track the monitor offset so we can add it back
                        mon_left = monitor["left"]
                        mon_top = monitor["top"]
                        
                        try:
                            # Configure tesseract path
                            tesseract_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe")
                            if os.path.exists(tesseract_path):
                                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                                
                            ocr_data = pytesseract.image_to_data(img, output_type=Output.DICT)
                            best_match_idx = -1
                            
                            target_lower = text_to_find.lower()
                            target_clean = "".join(c for c in target_lower if c.isalnum())
                            
                            # Log top OCR detections for debugging
                            debug_hits = []
                            for i, word in enumerate(ocr_data["text"]):
                                w_stripped = word.strip()
                                if w_stripped and len(debug_hits) < 5:
                                    debug_hits.append(f"'{w_stripped}'@({ocr_data['left'][i]},{ocr_data['top'][i]})")
                            logger.logger.info(f"Executor OCR: Looking for '{text_to_find}', first hits: {debug_hits}")
                            
                            for i, word in enumerate(ocr_data["text"]):
                                word_lower = word.strip().lower()
                                if not word_lower:
                                    continue
                                    
                                x = ocr_data["left"][i]
                                # Ignore hits on the right edge of the screen (the AI dashboard)
                                if x > self.screen_w - 420:
                                    continue
                                    
                                word_clean = "".join(c for c in word_lower if c.isalnum())
                                if target_clean in word_clean or word_clean in target_clean:
                                    best_match_idx = i
                                    logger.logger.info(f"Executor OCR: MATCHED '{word.strip()}' at index {i}")
                                    break
                                    
                            if best_match_idx != -1:
                                x = ocr_data["left"][best_match_idx]
                                y = ocr_data["top"][best_match_idx]
                                w = ocr_data["width"][best_match_idx]
                                h = ocr_data["height"][best_match_idx]
                                
                                # Center of the bounding box, offset by the monitor position
                                cx = mon_left + x + (w // 2)
                                cy = mon_top + y + (h // 2)
                                
                                logger.logger.info(f"Executor OCR: BBox=({x},{y},{w},{h}) center=({cx},{cy}) mon_offset=({mon_left},{mon_top})")
                                
                                jx = max(10, min(self.screen_w - 10, cx + random.randint(-1, 1)))
                                jy = max(10, min(self.screen_h - 10, cy + random.randint(-1, 1)))
                                
                                duration = random.uniform(0.3, 0.5)
                                pyautogui.moveTo(jx, jy, duration=duration, tween=pyautogui.easeOutQuad)
                                time.sleep(random.uniform(0.05, 0.15))
                                pyautogui.click(button=button, clicks=clicks)
                                logger.logger.info(f"Executor: OCR {button}-click x{clicks} at ({jx},{jy}) for text '{text_to_find}'")
                                
                                from core.state.short_term import short_term_memory
                                short_term_memory.add_system_context(
                                    f"CLICK_TEXT: Found '{text_to_find}' at ({cx}, {cy}), clicked successfully."
                                )
                                found = True
                        except Exception as e:
                            logger.logger.error(f"Executor OCR click failed: {e}")
                            
                    if not found:
                        from core.state.short_term import short_term_memory
                        short_term_memory.add_system_context(
                            f"CLICK_TEXT: Could not find '{text_to_find}' on screen using OCR."
                        )
                        logger.logger.warning(f"Executor: OCR could not find text '{text_to_find}'")
                else:
                    logger.logger.warning("click_text action missing 'text' field")


            elif a_type == "drag":
                x1, y1 = action.get("x1"), action.get("y1")
                x2, y2 = action.get("x2"), action.get("y2")
                if all(v is not None for v in [x1, y1, x2, y2]):
                    pyautogui.moveTo(x1, y1, duration=0.5)
                    time.sleep(0.1)
                    pyautogui.mouseDown()
                    time.sleep(0.1)
                    pyautogui.moveTo(x2, y2, duration=0.8, tween=pyautogui.easeOutQuad)
                    time.sleep(0.1)
                    pyautogui.mouseUp()
                    logger.logger.info(f"Executor: Dragged ({x1},{y1}) -> ({x2},{y2})")
                else:
                    logger.logger.warning(f"Drag action missing coordinates: {action}")
                    
            elif a_type == "type":
                text = action.get("text", "")
                if text:
                    # Always use clipboard paste — reliable across all apps including Discord
                    import pyperclip
                    pyperclip.copy(text)
                    time.sleep(0.15)
                    pyautogui.hotkey("ctrl", "v")
                    time.sleep(0.1)
                    # Clear clipboard to prevent re-pasting old content
                    pyperclip.copy("")
                    logger.logger.info(f"Executor: Pasted {len(text)} chars via clipboard")
                        
            elif a_type == "hotkey":
                keys = action.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                    
            elif a_type == "launch":
                target = action.get("target", "")
                if target:
                    success = window_manager.launch(target)
                    if success:
                        logger.log_event("APP_LAUNCHED", {"app": target})
                    else:
                        logger.logger.error(f"All launch attempts failed for: {target}")
                        bus.publish("ACTION_ABORTED", {"reason": f"Could not launch '{target}'"})
                        return
                else:
                    logger.logger.warning("Launch action missing target")
                        
            elif a_type == "switch":
                target = action.get("target", "")
                if target:
                    # Try to switch to running window first
                    switched = window_manager.switch_to(target)
                    if switched:
                        logger.logger.info(f"Executor: Switched to {target}")
                    else:
                        # If not running, launch it
                        logger.logger.info(f"Executor: '{target}' not running, launching it")
                        window_manager.launch(target)
                        
            elif a_type == "scroll":
                amount = action.get("amount", -3)
                pyautogui.scroll(amount)
                
            elif a_type == "open_url":
                url = action.get("url", "")
                if url:
                    import webbrowser
                    webbrowser.open(url)
                    logger.logger.info(f"Executor: Opened URL '{url}'")
                    time.sleep(1.0)  # Wait for browser to load
                
            elif a_type == "cmd":
                command = action.get("command", "")
                if command:
                    # SECURITY SANDBOX: Block dangerous commands
                    BLOCKED_PATTERNS = [
                        "format ", "format-volume", "remove-item -recurse -force /",
                        "rm -rf", "del /s /q c:\\", "rd /s /q c:\\",
                        "shutdown", "restart-computer", "stop-computer",
                        "set-executionpolicy", "reg delete", "reg add",
                        "invoke-webrequest", "invoke-restmethod",
                        "wget ", "curl ", "iwr ",
                        "new-service", "set-service",
                        "disable-windowsoptionalfeature",
                        "clear-disk", "initialize-disk",
                        "net user", "net localgroup",
                    ]
                    cmd_lower = command.lower().strip()
                    blocked = False
                    for pattern in BLOCKED_PATTERNS:
                        if pattern in cmd_lower:
                            blocked = True
                            logger.logger.error(f"SECURITY: Blocked dangerous command: {command}")
                            from core.state.short_term import short_term_memory
                            short_term_memory.add_system_context(
                                f"CMD_RESULT [BLOCKED BY SECURITY]:\nCommand: {command}\nReason: Contains blocked pattern '{pattern}'. This command could damage the system."
                            )
                            break
                    
                    if not blocked:
                        logger.logger.info(f"Executor: Running command '{command}'")
                        try:
                            result = subprocess.run(
                                ["powershell", "-NoProfile", "-Command", command],
                                capture_output=True, text=True, timeout=15
                            )
                            output = (result.stdout or "").strip()
                            errors = (result.stderr or "").strip()
                            
                            # Inject terminal output into AI memory for self-correction
                            from core.state.short_term import short_term_memory
                            if errors and result.returncode != 0:
                                short_term_memory.add_system_context(
                                    f"CMD_RESULT [FAILED, exit={result.returncode}]:\nCommand: {command}\nError: {errors[:1000]}"
                                )
                                logger.logger.warning(f"Executor: Command failed: {errors[:200]}")
                            elif output:
                                short_term_memory.add_system_context(
                                    f"CMD_RESULT [SUCCESS]:\nCommand: {command}\nOutput: {output[:1000]}"
                                )
                                logger.logger.info(f"Executor: Command succeeded with {len(output)} chars output")
                            else:
                                short_term_memory.add_system_context(
                                    f"CMD_RESULT [SUCCESS, no output]:\nCommand: {command}"
                                )
                                logger.logger.info("Executor: Command succeeded (no output)")
                        except subprocess.TimeoutExpired:
                            logger.logger.warning(f"Executor: Command timed out after 15s: {command}")
                            from core.state.short_term import short_term_memory
                            short_term_memory.add_system_context(
                                f"CMD_RESULT [TIMEOUT after 15s]:\nCommand: {command}"
                            )

            elif a_type == "create_skill":
                name = action.get("name", "")
                instruction = action.get("instruction", "")
                if name and instruction:
                    from core.engine.skill_manager import skill_manager
                    skill_manager.learn_skill(name, instruction)
                    logger.logger.info(f"Executor: Learned new skill '{name}'")
                    
            elif a_type == "read_file":
                path = action.get("path", "")
                if path and os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read(4000) # Read up to 4k chars to avoid blowing up context
                    from core.state.short_term import short_term_memory
                    short_term_memory.add_system_context(f"FILE_CONTENTS [{path}]:\n{content}")
                    logger.logger.info(f"Executor: Read file '{path}'")
                else:
                    logger.logger.warning(f"File not found: {path}")
                    
            elif a_type == "list_dir":
                path = action.get("path", ".")
                if os.path.exists(path):
                    files = os.listdir(path)
                    content = "\n".join(files[:50]) # max 50 items
                    from core.state.short_term import short_term_memory
                    short_term_memory.add_system_context(f"DIRECTORY_CONTENTS [{path}]:\n{content}")
                    logger.logger.info(f"Executor: Listed directory '{path}'")
                    
            elif a_type == "write_file":
                path = action.get("path", "")
                content = action.get("content", "")
                if path:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.logger.info(f"Executor: Wrote file '{path}'")
                    
            elif a_type == "extract_clipboard":
                import pyperclip
                # Trigger Ctrl+C to copy whatever is currently highlighted
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.2)
                clipboard_content = pyperclip.paste()
                if clipboard_content:
                    from core.state.short_term import short_term_memory
                    short_term_memory.add_system_context(f"EXTRACTED_CLIPBOARD_DATA:\n{clipboard_content}")
                    logger.logger.info(f"Executor: Extracted {len(clipboard_content)} chars from clipboard to memory.")
                else:
                    logger.logger.warning("Executor: Clipboard extraction failed or clipboard was empty.")
                    
            elif a_type == "listen_audio":
                duration = action.get("duration", 5)
                logger.logger.info(f"Executor: Listening to system audio for {duration}s...")
                try:
                    import soundcard as sc
                    import soundfile as sf
                    from core.ocr.stt_engine import stt_engine
                    
                    # Get loopback for default speaker
                    speaker = sc.default_speaker()
                    mic = sc.get_microphone(id=speaker.id, include_loopback=True)
                    
                    sample_rate = 16000
                    with mic.recorder(samplerate=sample_rate) as recorder:
                        data = recorder.record(numframes=int(sample_rate * duration))
                        
                    # Save to temp file
                    temp_wav = os.path.join(os.getcwd(), "temp_loopback.wav")
                    sf.write(temp_wav, data, sample_rate)
                    
                    # Transcribe
                    transcript = stt_engine.transcribe_audio(temp_wav)
                    if transcript and transcript.strip():
                        from core.state.short_term import short_term_memory
                        short_term_memory.add_system_context(f"SYSTEM_AUDIO_TRANSCRIPT ({duration}s):\n{transcript.strip()}")
                        logger.logger.info(f"Executor: Transcribed {len(transcript)} chars of system audio")
                    else:
                        logger.logger.warning("Executor: System audio contained no speech.")
                except Exception as e:
                    logger.logger.error(f"Executor: Audio capture failed - {e}")
                
            elif a_type == "ocr_screen":
                # Extract text from a screen region using Tesseract OCR
                x = action.get("x", 0)
                y = action.get("y", 0)
                w = action.get("w", self.screen_w)
                h = action.get("h", self.screen_h)
                try:
                    import mss
                    import pytesseract
                    from PIL import Image
                    
                    # Set Tesseract path (check common Windows install locations)
                    for tess_path in [
                        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
                        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                    ]:
                        if os.path.exists(tess_path):
                            pytesseract.pytesseract.tesseract_cmd = tess_path
                            break
                    
                    with mss.mss() as sct:
                        region = {"top": y, "left": x, "width": w, "height": h}
                        screenshot = sct.grab(region)
                        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                    
                    text = pytesseract.image_to_string(img).strip()
                    if text:
                        from core.state.short_term import short_term_memory
                        short_term_memory.add_system_context(f"OCR_EXTRACTED_TEXT [region: {x},{y} {w}x{h}]:\n{text[:2000]}")
                        logger.logger.info(f"Executor: OCR extracted {len(text)} chars from screen region")
                    else:
                        logger.logger.warning("Executor: OCR found no readable text in region")
                except ImportError:
                    logger.logger.warning("Executor: pytesseract not installed, falling back to full-screen OCR")
                except Exception as e:
                    logger.logger.error(f"Executor: OCR failed - {e}")
                
            time.sleep(random.uniform(0.1, 0.2))
            bus.publish("ACTION_COMPLETED", action)
            
        except pyautogui.FailSafeException:
            logger.logger.error("PyAutoGUI Fail-safe triggered (mouse in corner). Action aborted.")
            bus.publish("ACTION_ABORTED", {"reason": "Fail-safe triggered"})
        except Exception as e:
            logger.logger.error(f"Execution error: {e}")
            bus.publish("ACTION_ABORTED", {"reason": str(e)})

executor = ActionExecutor()
