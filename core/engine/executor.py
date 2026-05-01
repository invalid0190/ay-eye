import os
import pyautogui
import re
import subprocess
import time
import random
import threading
from core.engine.event_bus import bus
from core.engine.action_state import action_state
from core.engine.window_manager import window_manager
from core.utils.logger import logger
from core.vision.live_perception import live_perception

class ActionExecutor:
    _DIRECT_EXE_RE = re.compile(
        r"^\s*(?:&\s*)?(?P<quote>['\"])(?P<exe>[A-Za-z]:\\[^'\"]+\.exe)(?P=quote)(?P<args>.*)$",
        re.IGNORECASE,
    )

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

    def _desktop_bounds(self, frame=None):
        """Return inclusive desktop bounds in PyAutoGUI coordinates."""
        if frame:
            off_x, off_y = frame.desktop_offset
            raw_w, raw_h = frame.raw_size
            return off_x, off_y, off_x + raw_w - 1, off_y + raw_h - 1

        width, height = pyautogui.size()
        return 0, 0, width - 1, height - 1

    def _clamp_point(self, x, y, frame=None, margin=1):
        min_x, min_y, max_x, max_y = self._desktop_bounds(frame)
        safe_min_x = min_x + margin
        safe_min_y = min_y + margin
        safe_max_x = max_x - margin
        safe_max_y = max_y - margin

        if safe_min_x > safe_max_x:
            safe_min_x, safe_max_x = min_x, max_x
        if safe_min_y > safe_max_y:
            safe_min_y, safe_max_y = min_y, max_y

        return (
            int(max(safe_min_x, min(safe_max_x, x))),
            int(max(safe_min_y, min(safe_max_y, y))),
        )

    @staticmethod
    def _ps_quote(value):
        return "'" + value.replace("'", "''") + "'"

    @staticmethod
    def _detached_creationflags():
        return (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    def _try_launch_detached_command(self, command):
        """Launch direct GUI executable commands without capturing their stdio forever."""
        match = self._DIRECT_EXE_RE.match(command)
        if not match:
            return False

        exe_path = match.group("exe")
        args = match.group("args").strip()
        if not os.path.exists(exe_path):
            return False

        ps_command = f"Start-Process -FilePath {self._ps_quote(exe_path)}"
        if args:
            ps_command += f" -ArgumentList {self._ps_quote(args)}"

        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._detached_creationflags(),
            close_fds=True,
        )
        logger.logger.info(f"Executor: Detached GUI launch '{exe_path}'")
        from core.state.short_term import short_term_memory
        short_term_memory.add_system_context(
            f"CMD_RESULT [LAUNCHED]: Started '{exe_path}' without blocking the action executor."
        )
        return True

    @staticmethod
    def _clean_label(value):
        return "".join(ch for ch in (value or "").lower() if ch.isalnum())

    def _resolve_target_point(self, target):
        """Resolve a named target from the latest UI Automation state."""
        if not target:
            return None

        try:
            from core.state.manager import state_manager

            target_clean = self._clean_label(target)
            if not target_clean:
                return None

            best = None
            best_score = 0
            for element in state_manager.get_state().ui_elements:
                labels = [element.name, element.text, element.role]
                label_clean = " ".join(self._clean_label(label) for label in labels if label)
                if not label_clean:
                    continue

                score = 0
                if target_clean == self._clean_label(element.name):
                    score = 100
                elif target_clean == self._clean_label(element.text):
                    score = 95
                elif target_clean in label_clean:
                    score = 80
                elif label_clean in target_clean:
                    score = 65

                if score > best_score and element.rect and len(element.rect) >= 2:
                    best = element
                    best_score = score

            if not best:
                return None

            rect = best.rect
            if len(rect) >= 4:
                x = rect[0] + rect[2] / 2
                y = rect[1] + rect[3] / 2
            else:
                x, y = rect[0], rect[1]

            logger.logger.info(
                f"Executor: Resolved target '{target}' to UI element '{best.name}' at ({int(x)},{int(y)})"
            )
            return int(x), int(y)
        except Exception as e:
            logger.logger.warning(f"Executor: Target resolution failed for '{target}': {e}")
            return None

    @staticmethod
    def _indent_script(script):
        return "\n".join(f"    {line}" if line.strip() else "" for line in script.splitlines())

    def _send_python_to_blender_console(self, script, description="Blender script", restore_layout=True):
        """Run bpy code in the active Blender process using the Python console."""
        if not script or not script.strip():
            logger.logger.warning("Executor: Empty Blender Python script")
            return False

        switched = window_manager.switch_to("blender")
        if not switched:
            logger.logger.info("Executor: Blender is not focused, launching Blender before API action")
            window_manager.launch("blender")
            time.sleep(2.0)
            switched = window_manager.switch_to("blender")

        if not switched:
            from core.state.short_term import short_term_memory
            short_term_memory.add_system_context(
                f"BLENDER_API_RESULT [FAILED]: Could not focus or launch Blender for {description}."
            )
            return False

        start_msg = f"AYEYE_BLENDER_ACTION_START: {description}"
        done_msg = f"AYEYE_BLENDER_ACTION_DONE: {description}"
        wrapped = (
            "import traceback\n"
            f"print({start_msg!r})\n"
            "try:\n"
            f"{self._indent_script(script)}\n"
            f"    print({done_msg!r})\n"
            "except Exception:\n"
            "    traceback.print_exc()\n"
        )

        import pyperclip

        previous_clipboard = ""
        try:
            previous_clipboard = pyperclip.paste()
        except Exception:
            pass

        try:
            pyperclip.copy(f"exec({wrapped!r})")
            time.sleep(0.1)
            pyautogui.hotkey("shift", "f4")
            time.sleep(0.6)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            pyautogui.press("enter")
            time.sleep(0.8)
            if restore_layout:
                pyautogui.hotkey("shift", "f5")

            from core.state.short_term import short_term_memory
            short_term_memory.add_system_context(
                f"BLENDER_API_RESULT [SENT]: {description}. Watch for AYEYE_BLENDER_ACTION_DONE in Blender console."
            )
            logger.logger.info(f"Executor: Sent Blender Python action: {description}")
            return True
        finally:
            try:
                pyperclip.copy(previous_clipboard)
            except Exception:
                pass

    def _blender_import_script(self, filepath):
        safe_path = os.path.abspath(os.path.expandvars(os.path.expanduser(filepath)))
        return f"""
import os
import bpy

path = r{safe_path!r}
if not os.path.exists(path):
    raise FileNotFoundError(path)

ext = os.path.splitext(path)[1].lower()
before = len(bpy.data.objects)

if ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=path)
elif ext == ".obj":
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        bpy.ops.import_scene.obj(filepath=path)
elif ext in {{".glb", ".gltf"}}:
    bpy.ops.import_scene.gltf(filepath=path)
elif ext == ".stl":
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=path)
    else:
        bpy.ops.import_mesh.stl(filepath=path)
elif ext == ".ply":
    if hasattr(bpy.ops.wm, "ply_import"):
        bpy.ops.wm.ply_import(filepath=path)
    else:
        bpy.ops.import_mesh.ply(filepath=path)
elif ext == ".dae":
    bpy.ops.wm.collada_import(filepath=path)
elif ext == ".abc":
    bpy.ops.wm.alembic_import(filepath=path)
elif ext == ".usd" or ext == ".usda" or ext == ".usdc" or ext == ".usdz":
    bpy.ops.wm.usd_import(filepath=path)
elif ext == ".blend":
    bpy.ops.wm.open_mainfile(filepath=path)
else:
    raise ValueError(f"Unsupported import extension: {{ext}}")

after = len(bpy.data.objects)
print(f"AYEYE_IMPORT_RESULT: {{path}} objects_before={{before}} objects_after={{after}}")
"""

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
        
        frame_before = live_perception.get_latest_frame()
        
        try:
            if a_type == "click":
                x = action.get("x")
                y = action.get("y")
                button = action.get("button", "left")  # left, right, middle
                clicks = action.get("clicks", 1)        # 1 = single, 2 = double
                target_name = action.get("target", "")

                if (x is None or y is None) and target_name:
                    resolved = self._resolve_target_point(target_name)
                    if resolved:
                        x, y = resolved
                        action["x"] = x
                        action["y"] = y
                
                if x is not None and y is not None:
                    jx, jy = self._clamp_point(x, y, frame_before)
                    
                    duration = random.uniform(0.12, 0.25)
                    pyautogui.moveTo(jx, jy, duration=duration, tween=pyautogui.easeOutQuad)
                    time.sleep(0.05)
                    pyautogui.click(button=button, clicks=clicks)
                    logger.logger.info(f"Executor: {button}-click x{clicks} at ({jx},{jy})")
                    
                    # Inject click feedback into memory for AI self-correction
                    from core.state.short_term import short_term_memory
                    short_term_memory.add_system_context(
                        f"CLICK_EXECUTED: {button}-click x{clicks} at pixel ({jx},{jy}) targeting '{target_name or 'coordinate target'}'"
                    )
                else:
                    logger.logger.warning(f"Click action missing coordinates: {action}")
                    bus.publish("ACTION_ABORTED", {"reason": f"Click target could not be resolved: {action}"})
                    return
                    
            elif a_type == "click_text":
                text_to_find = action.get("text", "")
                button = action.get("button", "left")
                clicks = action.get("clicks", 1)
                
                if text_to_find:
                    # --- Special case: Ay-Eye own UI buttons ---
                    text_upper = text_to_find.strip().upper()
                    if text_upper == "CONFIRM":
                        pyautogui.hotkey("alt", "Return")
                        logger.logger.info("Executor: CONFIRM intercepted -> Alt+Enter")
                        from core.state.short_term import short_term_memory
                        short_term_memory.add_system_context("CLICK_TEXT: 'CONFIRM' -> pressed Alt+Enter (Ay-Eye confirm hotkey)")
                        time.sleep(0.3)
                        live_perception.verify_screen_changed(frame_before)
                        bus.publish("ACTION_COMPLETED", action)
                        return
                    elif text_upper == "DISMISS":
                        pyautogui.press("escape")
                        logger.logger.info("Executor: DISMISS intercepted -> Escape")
                        from core.state.short_term import short_term_memory
                        short_term_memory.add_system_context("CLICK_TEXT: 'DISMISS' -> pressed Escape (Ay-Eye dismiss)")
                        time.sleep(0.3)
                        live_perception.verify_screen_changed(frame_before)
                        bus.publish("ACTION_COMPLETED", action)
                        return
                    
                    # --- Fast-fail for Blender (OCR can't read its OpenGL fonts) ---
                    try:
                        active_title = ""
                        import ctypes
                        hwnd = ctypes.windll.user32.GetForegroundWindow()
                        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                            active_title = buf.value.lower()
                    except:
                        active_title = ""
                    
                    if "blender" in active_title:
                        from core.state.short_term import short_term_memory
                        short_term_memory.add_system_context(
                            f"CLICK_TEXT BLOCKED: Blender is active. OCR cannot read Blender's OpenGL fonts. "
                            f"Use keyboard shortcuts instead: Ctrl+O=Open, Ctrl+N=New, F3=Search command, Shift+A=Add menu. "
                            f"Or use coordinate-based click with the grid."
                        )
                        logger.logger.warning(f"Executor: click_text blocked — Blender active, OCR won't work")
                        bus.publish("ACTION_COMPLETED", action)
                        return
                    
                    import mss
                    from PIL import Image
                    import pytesseract
                    from pytesseract import Output
                    
                    found = False
                    with mss.mss() as sct:
                        # Search the full virtual desktop so OCR clicks work on any monitor.
                        monitor = sct.monitors[0]
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
                            
                            # Build a list of valid OCR entries (non-empty, with positions)
                            entries = []
                            for i in range(len(ocr_data["text"])):
                                word = ocr_data["text"][i].strip()
                                if not word:
                                    continue
                                x = ocr_data["left"][i]
                                entries.append({
                                    "idx": i, "text": word,
                                    "x": x, "y": ocr_data["top"][i],
                                    "w": ocr_data["width"][i], "h": ocr_data["height"][i],
                                    "line": ocr_data["line_num"][i], "block": ocr_data["block_num"][i]
                                })
                            
                            # Log top OCR detections for debugging
                            debug_hits = [f"'{e['text']}'@({e['x']},{e['y']})" for e in entries[:10]]
                            logger.logger.info(f"Executor OCR: Looking for '{text_to_find}', detections ({len(entries)} total): {debug_hits}")
                            
                            # --- PASS 1: Exact or near-exact single-word match ---
                            for e in entries:
                                word_clean = "".join(c for c in e["text"].lower() if c.isalnum())
                                if not word_clean or len(word_clean) < 2:
                                    continue
                                # Exact match (case-insensitive, ignoring punctuation)
                                if target_clean == word_clean:
                                    best_match_idx = e["idx"]
                                    logger.logger.info(f"Executor OCR: EXACT match '{e['text']}' at ({e['x']},{e['y']})")
                                    break
                                # Substring match but ONLY if lengths are similar (avoid 'e' matching 'file')
                                min_len = min(len(target_clean), len(word_clean))
                                max_len = max(len(target_clean), len(word_clean))
                                if min_len >= 3 and min_len >= max_len * 0.5:
                                    if target_clean in word_clean or word_clean in target_clean:
                                        best_match_idx = e["idx"]
                                        logger.logger.info(f"Executor OCR: PASS1 substr match '{e['text']}' at ({e['x']},{e['y']})")
                                        break
                            
                            # --- PASS 2: Multi-word phrase match (sliding window) ---
                            if best_match_idx == -1 and len(target_clean) > 3:
                                for start_i, start_entry in enumerate(entries):
                                    phrase = start_entry["text"]
                                    phrase_clean = "".join(c for c in phrase.lower() if c.isalnum())
                                    
                                    if target_clean in phrase_clean:
                                        best_match_idx = start_entry["idx"]
                                        logger.logger.info(f"Executor OCR: PASS2 matched phrase '{phrase}' at ({start_entry['x']},{start_entry['y']})")
                                        break
                                    
                                    # Extend phrase with adjacent words on the same line
                                    for next_i in range(start_i + 1, min(start_i + 5, len(entries))):
                                        next_entry = entries[next_i]
                                        # Only merge words on the same text line
                                        if next_entry["line"] != start_entry["line"] or next_entry["block"] != start_entry["block"]:
                                            break
                                        phrase += " " + next_entry["text"]
                                        phrase_clean = "".join(c for c in phrase.lower() if c.isalnum())
                                        
                                        if target_clean in phrase_clean or phrase_clean in target_clean:
                                            # Use the midpoint of the full phrase span
                                            best_match_idx = start_entry["idx"]
                                            # Override bbox to cover the full phrase
                                            ocr_data["width"][start_entry["idx"]] = (next_entry["x"] + next_entry["w"]) - start_entry["x"]
                                            logger.logger.info(f"Executor OCR: PASS2 matched multi-word phrase '{phrase}' spanning {start_i}-{next_i}")
                                            break
                                    if best_match_idx != -1:
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
                                
                                jx, jy = self._clamp_point(cx, cy, frame_before)
                                
                                duration = random.uniform(0.12, 0.25)
                                pyautogui.moveTo(jx, jy, duration=duration, tween=pyautogui.easeOutQuad)
                                time.sleep(0.05)
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
                            f"CLICK_TEXT FAILED: Could not find '{text_to_find}' on screen using OCR. "
                            f"This app may use custom-rendered fonts that OCR cannot read (like Blender or game engines). "
                            f"FALLBACK OPTIONS: 1) Use coordinate-based click with the grid overlay. "
                            f"2) Use keyboard shortcuts instead (e.g. hotkey for File menu). "
                            f"3) Try a shorter or slightly different text label."
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
                        # Smart intercept: if the command is just an app name, use launch instead
                        # This handles cases where AI says cmd "blender" but blender isn't in PATH
                        app_launch_names = {"blender", "discord", "spotify", "telegram", "slack", "chrome", "firefox", "brave", "notepad", "code", "vscode"}
                        cmd_stripped = cmd_lower.strip().strip("'\"")
                        if self._try_launch_detached_command(command):
                            time.sleep(0.5)
                        elif cmd_stripped in app_launch_names or cmd_stripped.startswith("start-process"):
                            # Extract app name from Start-Process command
                            app_name = cmd_stripped
                            if "start-process" in cmd_stripped:
                                # Parse: Start-Process 'blender' -> blender
                                parts = command.strip().split()
                                if len(parts) >= 2:
                                    app_name = parts[-1].strip("'\"")
                            
                            logger.logger.info(f"Executor: Intercepted cmd '{command}' -> using window_manager.launch('{app_name}')")
                            success = window_manager.launch(app_name)
                            if success:
                                from core.state.short_term import short_term_memory
                                short_term_memory.add_system_context(f"CMD_RESULT [SUCCESS]: Launched '{app_name}' via system launcher.")
                            else:
                                from core.state.short_term import short_term_memory
                                short_term_memory.add_system_context(f"CMD_RESULT [FAILED]: Could not launch '{app_name}'.")
                        else:
                            logger.logger.info(f"Executor: Running command '{command}'")
                            try:
                                result = subprocess.run(
                                    ["powershell", "-NoProfile", "-Command", command],
                                    stdin=subprocess.DEVNULL,
                                    capture_output=True,
                                    text=True,
                                    timeout=15,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                    close_fds=True,
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

            elif a_type == "blender_python":
                script = action.get("script", "")
                description = action.get("description", "custom Blender Python")
                restore_layout = action.get("restore_layout", True)
                success = self._send_python_to_blender_console(script, description, restore_layout)
                if not success:
                    bus.publish("ACTION_ABORTED", {"reason": f"Blender API action failed: {description}"})
                    return

            elif a_type == "blender_open_import_menu":
                script = "import bpy\nbpy.ops.wm.call_menu(name='TOPBAR_MT_file_import')"
                success = self._send_python_to_blender_console(
                    script,
                    "open Blender Import menu",
                    restore_layout=False,
                )
                if not success:
                    bus.publish("ACTION_ABORTED", {"reason": "Could not open Blender import menu through API"})
                    return

            elif a_type == "blender_import_file":
                filepath = action.get("path") or action.get("filepath") or action.get("file")
                if not filepath:
                    logger.logger.warning("Blender import action missing path")
                    bus.publish("ACTION_ABORTED", {"reason": "Blender import action missing file path"})
                    return
                script = self._blender_import_script(filepath)
                success = self._send_python_to_blender_console(
                    script,
                    f"import Blender file {filepath}",
                    restore_layout=True,
                )
                if not success:
                    bus.publish("ACTION_ABORTED", {"reason": f"Could not import file in Blender: {filepath}"})
                    return

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
                if frame_before:
                    desk_w, desk_h = frame_before.raw_size
                else:
                    desk_w, desk_h = self.screen_w, self.screen_h
                w = action.get("w", desk_w)
                h = action.get("h", desk_h)
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
            
            # Post action verification
            if a_type in ["click", "click_text", "type", "hotkey"]:
                time.sleep(0.3)
                live_perception.verify_screen_changed(frame_before)
                
            bus.publish("ACTION_COMPLETED", action)
            
        except pyautogui.FailSafeException:
            logger.logger.error("PyAutoGUI Fail-safe triggered (mouse in corner). Action aborted.")
            bus.publish("ACTION_ABORTED", {"reason": "Fail-safe triggered"})
        except Exception as e:
            logger.logger.error(f"Execution error: {e}")
            bus.publish("ACTION_ABORTED", {"reason": str(e)})

executor = ActionExecutor()
