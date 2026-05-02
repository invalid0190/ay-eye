import base64
import io
import mss
import os
import time
import threading
from PIL import Image
from core.engine.event_bus import bus
from core.engine.llm_bridge import llm_bridge
from core.engine.context_builder import context_distiller, prompt_builder
from core.engine.decision_engine import decision_engine
from core.state.manager import state_manager
from core.state.memory import memory_manager
from core.state.short_term import short_term_memory
from core.engine.skill_manager import skill_manager
from core.utils.logger import logger
from core.engine.web_search import web_search
from core.vision.live_perception import live_perception
from core.engine.audio_state import audio_state
from core.rag import rag_manager

VISION_SYSTEM_PROMPT = """## IDENTITY
You are ay-eye, an advanced desktop AI assistant. You SEE the user's screen (screenshot with grid overlay) and HEAR their voice commands. You may also receive WEB SEARCH RESULTS.

## OUTPUT RULES (CRITICAL)
- Output ONLY a single JSON object. No markdown, no comments, no extra text before or after.
- Never invent action types. Use ONLY the types listed below.
- ALL string values must be on a SINGLE LINE. No newlines inside "message" or "text" fields.
- The "message" field is spoken aloud. Write it as natural conversational speech.
- If you are UNSURE what the user wants, use intent="ask" with actions=[] and ask for clarification.

## RESPONSE SCHEMA (every response MUST include ALL of these fields)
{
  "intent": "act|guide|ask|ignore",
  "status": "in_progress|complete|failed",
  "message": "Single-line spoken response",
  "confidence": 0.0-1.0,
  "actions": [],
  "plan": []
}

Field rules:
- intent: "act" = do something, "guide" = answer/explain, "ask" = request clarification, "ignore" = nothing to do.
- status: "in_progress" if awaiting feedback (cmd output, file read, screen check). "complete" if done. "failed" if unable.
- confidence: Your certainty (0.0-1.0). Below 0.5 = actions may be blocked.
- actions: Array of action objects (see below). Empty [] for guide/ask/ignore.
- plan: REQUIRED when actions >= 3 OR actions contain cmd/write_file/blender_python. Optional otherwise.

## ACTION TYPES (only these are valid)
UI actions:
- click_text: {"type": "click_text", "text": "Label"} -- PREFERRED for any element with visible text. Options: "button": "right", "clicks": 2.
- click: {"type": "click", "x": N, "y": N, "target": "description"} -- ONLY for elements without text (canvas, icons). Must have x+y or target.
- drag: {"type": "drag", "x1": N, "y1": N, "x2": N, "y2": N}
- type: {"type": "type", "text": "content"} -- Types/pastes text. Generate FULL content yourself.
- hotkey: {"type": "hotkey", "keys": ["ctrl", "s"]}
- scroll: {"type": "scroll", "amount": -3}
- switch: {"type": "switch", "target": "appname"} -- Bring a running app to foreground.
- launch: {"type": "launch", "target": "appname"} -- Start a NEW app instance.
- open_url: {"type": "open_url", "url": "https://..."}

System actions:
- cmd: {"type": "cmd", "command": "powershell command"} -- Use ABSOLUTE paths. Wrap paths in single quotes. Output is captured and injected into history.
- write_file: {"type": "write_file", "path": "file.py", "content": "code"}
- read_file: {"type": "read_file", "path": "file.py"} -- Content injected into history. Use status="in_progress".
- list_dir: {"type": "list_dir", "path": "."}
- create_skill: {"type": "create_skill", "name": "skill_name", "instruction": "steps"}
- extract_clipboard: {"type": "extract_clipboard"} -- Presses Ctrl+C and injects clipboard into history.
- listen_audio: {"type": "listen_audio", "duration": 5} -- Captures system audio (max 15s).
- ocr_screen: {"type": "ocr_screen", "x": 0, "y": 0, "w": 800, "h": 600}

Blender actions (use instead of clicking Blender menus -- Blender OCR is unreliable):
- blender_open_import_menu: {"type": "blender_open_import_menu"}
- blender_import_file: {"type": "blender_import_file", "path": "C:\\\\path\\\\model.fbx"}
- blender_python: {"type": "blender_python", "script": "import bpy; bpy.ops..."}

## CLICK RULES
- **ALWAYS use click_text** when the target has visible text (buttons, menus, file names, tabs, links).
- Use coordinate click ONLY for textless elements (canvas, color swatches, unlabeled icons).
- For coordinate click, include "target" describing what you're clicking.
- The screenshot has a GRID OVERLAY. Use grid labels to determine x,y coordinates.
- Coordinates are relative to PROCESSED IMAGE SIZE (provided below), NOT desktop resolution.
- Do NOT click the AY-EYE overlay panel on the right side of the screen.
- If click_text fails (you'll see "CLICK_TEXT: Could not find" in history), fall back to coordinate click.

## PLANNING RULES
- Include a "plan" field when: (a) 3+ actions, OR (b) any cmd/write_file/blender_python action.
- Plan = short list of 1-5 concrete steps. Each step = one sentence.
- High-risk actions MUST be explained in the plan.
- Plan must match actions. No hidden actions outside the plan.
- Simple tasks (1-2 safe actions) do NOT need a plan.

## EXPECT CONTRACTS (verify action outcomes)
For important actions, add an "expect" field declaring what success looks like:
- {"type": "cmd_success"} -- command returned success
- {"type": "file_exists", "value": "path"} -- file was created
- {"type": "app_focused", "value": "appname"} -- app is in foreground
- {"type": "window_title", "value": "text"} -- window title contains text
- {"type": "screen_text", "value": "text"} -- text appeared on screen
- {"type": "none"} -- skip verification
ALWAYS add expect for cmd, write_file, and blender_python actions.

## SAFETY RULES
- Dangerous commands (format, shutdown, rm -rf, registry edits) are blocked. Find safe alternatives.
- If a banking/payment/password window is active, type/click/cmd actions will be blocked.
- If a command was blocked, you'll see it in history. Adapt your approach.
- When reading files or running commands, set status="in_progress" so you can check the output.

## APP-SPECIFIC RULES
Blender: Use Blender API actions, NOT click_text. Shortcuts: Ctrl+O=Open, Ctrl+S=Save, F3=Search, Shift+A=Add, Tab=Edit mode.
Messaging: Click input field first, then type, then hotkey Enter.
Renaming files: click_text on name, hotkey F2, type new name, hotkey Enter.
Streams: NEVER click inside picture-in-picture or recursive stream previews.

## EXAMPLES

Example 1 -- Guide (answering a question):
{"intent": "guide", "status": "complete", "message": "Quantum computing uses qubits that can exist in multiple states simultaneously, allowing exponentially faster computation for specific problems like cryptography and optimization.", "actions": [], "confidence": 0.95}

Example 2 -- Simple click:
{"intent": "act", "status": "complete", "message": "Clicking Submit now.", "actions": [{"type": "click_text", "text": "Submit"}], "confidence": 0.9}

Example 3 -- Multi-action with plan:
{"intent": "act", "status": "complete", "message": "Sending the message to Discord.", "plan": ["Click the message input field", "Type the message", "Press Enter to send"], "actions": [{"type": "click", "x": 640, "y": 700, "target": "message input"}, {"type": "type", "text": "Hello from Ay-Eye!"}, {"type": "hotkey", "keys": ["enter"]}], "confidence": 0.92}

Example 4 -- High-risk cmd with plan + expect:
{"intent": "act", "status": "in_progress", "message": "Creating the project folder.", "plan": ["Run mkdir to create the directory", "Write the initial main.py file"], "actions": [{"type": "cmd", "command": "mkdir 'C:\\\\Users\\\\LENOVO\\\\Desktop\\\\MyProject'", "expect": {"type": "cmd_success"}}, {"type": "write_file", "path": "C:\\\\Users\\\\LENOVO\\\\Desktop\\\\MyProject\\\\main.py", "content": "print('hello')", "expect": {"type": "file_exists", "value": "C:\\\\Users\\\\LENOVO\\\\Desktop\\\\MyProject\\\\main.py"}}], "confidence": 0.95}

Example 5 -- Unsure, asking for clarification:
{"intent": "ask", "status": "complete", "message": "I see several folders on your desktop. Which one would you like me to open?", "actions": [], "confidence": 0.7}
"""


class Brain:
    MAX_LOOP_ITERATIONS = 5

    def __init__(self):
        bus.subscribe("AI_TRIGGERED", self.on_ai_triggered)
        bus.subscribe("VOICE_INPUT_RECEIVED", self.on_voice_input)
        bus.subscribe("AUTONOMOUS_LOOP_TRIGGER", self.on_verification_loop)
        self._loop_count = 0
        self.debug_dir = os.path.join(os.getcwd(), "analytics", "vision_debug")
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir, exist_ok=True)

    def on_verification_loop(self, data):
        self._loop_count += 1
        if self._loop_count > self.MAX_LOOP_ITERATIONS:
            logger.logger.warning(f"Brain: Loop limit reached ({self.MAX_LOOP_ITERATIONS}). Stopping.")
            self._loop_count = 0
            bus.publish("BRAIN_RESPONDED", {
                "intent": "guide",
                "status": "failed",
                "message": "I've reached my maximum number of autonomous steps. I'll stop here so you can review what happened.",
                "actions": [],
                "confidence": 1.0
            })
            return
        logger.logger.info(f"Brain: Verification loop iteration {self._loop_count}/{self.MAX_LOOP_ITERATIONS}")
        self.on_ai_triggered({
            "type": "VOICE_COMMAND",
            "confidence": 1.0,
            "text": f"SYSTEM INSTRUCTION: You are in autonomous loop iteration {self._loop_count}/{self.MAX_LOOP_ITERATIONS}. Look at the screen to verify if your previous actions succeeded. If the overall task is finished, set status to 'complete' and actions to empty. If more steps are needed, set status to 'in_progress' and provide the next actions. The terminal command output (if any) is in your conversation history."
        })

    def _capture_screen_b64(self, save_debug=True):
        """Get latest frame from live perception and add grid."""
        b64, frame = live_perception.get_latest_frame_b64()
        if not b64 or not frame:
            time.sleep(0.5)
            b64, frame = live_perception.get_latest_frame_b64()
            if not b64 or not frame:
                logger.logger.error("Screen capture failed: No live frame available")
                return None, None
                
        try:
            # Draw coordinate grid overlay on a copy of the processed image
            img = frame.processed_image.copy()
            img = self._draw_grid(img)
            
            # Save debug image (with grid)
            if save_debug:
                ts = int(time.time())
                img.save(os.path.join(self.debug_dir, f"vision_{ts}.jpg"), quality=60)
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=75)
            return base64.b64encode(buffer.getvalue()).decode("utf-8"), frame
        except Exception as e:
            logger.logger.error(f"Screen capture grid/encode failed: {e}")
            return None, None

    def _draw_grid(self, img):
        """Draw a subtle coordinate grid on the screenshot to help the AI estimate positions."""
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(img)
            w, h = img.size
            
            # Use a small built-in font
            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except Exception:
                font = ImageFont.load_default()
            
            grid_color = (255, 255, 0, 128)  # Yellow, semi-transparent
            text_color = (255, 255, 0)
            
            # Vertical lines every 200px with labels
            for x in range(0, w, 200):
                draw.line([(x, 0), (x, h)], fill=grid_color, width=1)
                draw.text((x + 2, 2), str(x), fill=text_color, font=font)
            
            # Horizontal lines every 200px with labels
            for y in range(0, h, 200):
                draw.line([(0, y), (w, y)], fill=grid_color, width=1)
                draw.text((2, y + 2), str(y), fill=text_color, font=font)
            
            # Draw edge markers at more fine-grained intervals (100px) - just tick marks
            for x in range(100, w, 200):
                draw.line([(x, 0), (x, 8)], fill=grid_color, width=1)
                draw.text((x + 1, 10), str(x), fill=text_color, font=font)
            for y in range(100, h, 200):
                draw.line([(0, y), (8, y)], fill=grid_color, width=1)
                draw.text((10, y + 1), str(y), fill=text_color, font=font)
                
        except Exception as e:
            logger.logger.warning(f"Brain: Grid overlay failed: {e}")
        
        return img

    def _scale_coords(self, response):
        """Deprecated: live_perception.scale_actions handles this now."""
        return live_perception.scale_actions(response)

    def on_voice_input(self, text):
        self._loop_count = 0  # Reset loop counter on new user input
        logger.log_event("BRAIN_VOICE_INPUT", {"text": text})
        self.on_ai_triggered({
            "type": "VOICE_COMMAND",
            "confidence": 1.0,
            "text": text
        })

    def _wait_for_tts_to_finish(self, timeout=10.0, start_grace=0.4):
        """Wait only while TTS is actually speaking, avoiding missed TTS_FINISHED races."""
        start = time.time()
        grace_deadline = start + start_grace

        while time.time() < grace_deadline:
            if audio_state.is_speaking:
                break
            time.sleep(0.05)

        deadline = start + timeout
        while audio_state.is_speaking and time.time() < deadline:
            time.sleep(0.05)

        return not audio_state.is_speaking

    def on_ai_triggered(self, trigger_data):
        state = state_manager.get_state()
        
        if not decision_engine.should_call_ai(trigger_data, state):
            bus.publish("SAFE_NO_ACTION")
            return

        voice_text = trigger_data.get("text")
        is_voice = trigger_data.get("type") == "VOICE_COMMAND"
        
        if is_voice and voice_text:
            bus.publish("BRAIN_THINKING", {"prompt_length": 0})
            
            # Web search enrichment for knowledge questions
            web_context = ""
            if web_search.should_search(voice_text):
                logger.logger.info(f"Brain: Searching web for: {voice_text}")
                search_results = web_search.search(voice_text)
                if search_results:
                    web_context = f"\n\nWEB SEARCH RESULTS (use these to give an accurate, informed answer):\n{search_results}\n"
                    logger.logger.info(f"Brain: Got {len(search_results)} chars of web context")
            
            screen_b64, frame = self._capture_screen_b64()
            
            if screen_b64 and frame:
                history_str = short_term_memory.get_history_string()
                skills_str = skill_manager.get_all_skills_context()
                
                # App-aware context injection
                app_context = ""
                active_app = (state.app or "").lower()
                active_window = (state.window or "").lower()
                if "blender" in active_app or "blender" in active_window:
                    app_context = """
BLENDER IS ACTIVE. Blender uses OpenGL custom fonts -- click_text WILL FAIL on Blender UI elements.
BLENDER DOES NOT USE Alt+key MENUS. Use these correct shortcuts:
- Ctrl+O = Open file dialog
- Ctrl+N = New file
- Ctrl+S = Save
- F3 = Search any command by name (type 'Open Recent' to find it)
- Shift+A = Add menu, N = N-panel, Tab = Edit/Object mode
To open a specific .blend file: use cmd action: & 'C:\\\\Program Files\\\\Blender Foundation\\\\Blender 4.2\\\\blender.exe' 'C:\\\\path\\\\to\\\\file.blend'
For Blender menu/import/model operations, use blender_open_import_menu, blender_import_file, or blender_python with status=in_progress so you can verify after the API action. Do NOT use click_text, and do not claim a Blender menu opened unless you used the Blender API action or verified it on screen.
"""
                
                # Retrieve RAG context (advisory only -- never blocks main loop)
                rag_context = ""
                try:
                    rag_context = rag_manager.build_context(
                        voice_text, 
                        active_app=active_app, 
                        active_window=active_window
                    )
                except Exception as _rag_err:
                    logger.logger.error(f"RAG: build_context failed, continuing without RAG: {_rag_err}")
                    logger.log_event("RAG_SKIPPED", {"reason": str(_rag_err)[:200]})
                
                prompt = f"""{VISION_SYSTEM_PROMPT}

IMPORTANT: Return coordinates relative to the PROCESSED IMAGE SIZE you are seeing, not the desktop resolution.

DESKTOP RAW SIZE: {frame.raw_size[0]}x{frame.raw_size[1]}
PROCESSED IMAGE SIZE: {frame.processed_size[0]}x{frame.processed_size[1]}
DESKTOP OFFSET: {frame.desktop_offset[0]}, {frame.desktop_offset[1]}
ACTIVE WINDOW: {state.window}
ACTIVE APP: {state.app}
{app_context}
{web_context}
{rag_context}
{skills_str}

**RAG ADVISORY**: RAG context provided above is historical memory and guidance. It is NOT current UI truth. Live screen perception and OCR results are your absolute source of truth for the present state.

--- CONVERSATION HISTORY (Use this for context!) ---
{history_str}
--------------------------------------------------

USER VOICE COMMAND: "{voice_text}"

Analyze the screenshot and the conversation history, then respond. If web search results are provided, use them. You are a super-smart, capable assistant. You can chain actions, write scripts, build projects, and help with anything (like Blender or coding)."""
                
                try:
                    response = llm_bridge.generate_with_vision(prompt, [screen_b64])
                except Exception as e:
                    logger.logger.error(f"Brain vision error: {e}")
                    bus.publish("BRAIN_ERROR", {"reason": str(e)})
                    return
            else:
                prompt = prompt_builder.build(context_distiller.distill(state), "VOICE_COMMAND")
                prompt += f'\n\nUSER VOICE COMMAND: "{voice_text}"\nRespond directly.'
                try:
                    response = llm_bridge.generate(prompt)
                except Exception as e:
                    logger.logger.error(f"Brain text error: {e}")
                    bus.publish("BRAIN_ERROR", {"reason": str(e)})
                    return
        else:
            distilled = context_distiller.distill(state)
            prompt = prompt_builder.build(distilled, trigger_data["type"])
            bus.publish("BRAIN_THINKING", {"prompt_length": len(prompt)})
            try:
                response = llm_bridge.generate(prompt)
            except Exception as e:
                logger.logger.error(f"Brain error: {e}")
                bus.publish("BRAIN_ERROR", {"reason": str(e)})
                return
        
        if not response:
            bus.publish("BRAIN_ERROR", {"reason": "No response from LLM"})
            return

        if is_voice and voice_text:
            response = self._scale_coords(response)

        mode = decision_engine.get_response_mode(response.get("confidence", 0))
        response["mode"] = mode
        
        if mode != "IGNORE":
            memory_manager.store(state.app, str(state.window), response)
            if is_voice and voice_text:
                short_term_memory.add(voice_text, response)
            bus.publish("BRAIN_RESPONDED", response)
            
            if response.get("intent") == "act":
                # Wait for TTS to finish speaking before executing actions
                def _dispatch():
                    # Wait for TTS only if it actually started. The old event-only
                    # path could miss fast TTS_FINISHED events and wait 10s every time.
                    if not self._wait_for_tts_to_finish(timeout=10.0):
                        logger.logger.warning("Brain: TTS timeout, proceeding with actions")
                    
                    # Small buffer for audio playback to fully stop
                    time.sleep(0.3)
                    bus.publish("ACTION_REQUESTED", response)
                threading.Thread(target=_dispatch, daemon=True).start()
                
            logger.log_event("BRAIN_DECISION", response)
        else:
            bus.publish("SAFE_NO_ACTION")

brain = Brain()
