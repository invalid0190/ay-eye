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
            time.sleep(random.uniform(0.1, 0.3))
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
                
                if x is not None and y is not None:
                    jx = max(10, min(self.screen_w - 10, x + random.randint(-2, 2)))
                    jy = max(10, min(self.screen_h - 10, y + random.randint(-2, 2)))
                    
                    duration = random.uniform(0.8, 1.2)
                    pyautogui.moveTo(jx, jy, duration=duration, tween=pyautogui.easeOutQuad)
                    time.sleep(random.uniform(0.05, 0.15))
                    pyautogui.click()
                else:
                    logger.logger.warning(f"Click action missing coordinates: {action}")
                    
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
                
            elif a_type == "cmd":
                command = action.get("command", "")
                capture = action.get("capture_output", True) # Default to True for smarter RPA
                if command:
                    logger.logger.info(f"Executor: Running command '{command}' (capture={capture})")
                    try:
                        if capture:
                            # Run and wait for output
                            result = subprocess.run(
                                f'powershell -Command "{command}"', 
                                shell=True, 
                                capture_output=True, 
                                text=True, 
                                timeout=30
                            )
                            output = (result.stdout + "\n" + result.stderr).strip()
                            if output:
                                from core.state.short_term import short_term_memory
                                short_term_memory.add_system_context(f"COMMAND_OUTPUT:\n{output[:2000]}")
                                logger.logger.info(f"Executor: Captured {len(output)} chars of output")
                        else:
                            # Fire and forget
                            subprocess.Popen(f'powershell -Command "{command}"', shell=True)
                            time.sleep(0.5)
                    except subprocess.TimeoutExpired:
                        logger.logger.error("Executor: Command timed out after 30s")
                    except Exception as e:
                        logger.logger.error(f"Executor: Command failed: {e}")

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
                
            time.sleep(random.uniform(0.1, 0.2))
            bus.publish("ACTION_COMPLETED", action)
            
        except pyautogui.FailSafeException:
            logger.logger.error("PyAutoGUI Fail-safe triggered (mouse in corner). Action aborted.")
            bus.publish("ACTION_ABORTED", {"reason": "Fail-safe triggered"})
        except Exception as e:
            logger.logger.error(f"Execution error: {e}")
            bus.publish("ACTION_ABORTED", {"reason": str(e)})

executor = ActionExecutor()
