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

VISION_SYSTEM_PROMPT = """You are ay-eye, an advanced desktop AI assistant. You can SEE the user's screen and HEAR their voice commands. You also may receive WEB SEARCH RESULTS for knowledge questions.

### How to Respond:

**1. ANSWERING QUESTIONS (intent: "guide")**
When the user asks a question ("What is X?", "How does Y work?", "Tell me about Z"):
- Put the COMPLETE, DETAILED answer in the "message" field. This is what you will speak aloud.
- Do NOT just say "Here's an explanation..." — actually GIVE the full explanation.
- If web search results are provided, synthesize them into a clear, conversational answer.
- Use intent "guide" with an empty actions array.
- Example: User asks "What is quantum computing?"
  → message: "Quantum computing uses quantum bits or qubits that can exist in multiple states simultaneously, unlike classical bits. This allows quantum computers to solve certain problems exponentially faster, like cryptography, drug discovery, and optimization problems."

**2. SCREEN ACTIONS (intent: "act")**
When the user wants you to DO something on screen (click, type, open, close, scroll):
- Use precise actions: click, type, hotkey, launch, switch, scroll, drag.
- For RIGHT-CLICK (context menus): `{"type": "click", "x": 100, "y": 200, "button": "right"}`
- For DOUBLE-CLICK (open files): `{"type": "click", "x": 100, "y": 200, "clicks": 2}`
- For DRAG-AND-DROP (move files, resize): `{"type": "drag", "x1": 100, "y1": 200, "x2": 400, "y2": 300}`
- For OPENING URLS directly: `{"type": "open_url", "url": "https://google.com"}`
- Keep the "message" field as a short verbal confirmation of what you're doing.

### CRITICAL COORDINATE RULES:
- The screenshot has a GRID OVERLAY with numbered axis labels on the edges.
- USE THE GRID to determine coordinates. The numbers on the left/top edges tell you pixel positions.
- Coordinates (0,0) = top-left corner of the image.
- Your x,y values MUST be in the PROCESSED IMAGE coordinate space (see PROCESSED IMAGE SIZE below).
- To click the CENTER of an icon, estimate where the icon center is using the grid markers.
- COMMON MISTAKE: Do NOT confuse left-side icons with right-side icons. Use the grid X-axis labels to verify.
- The AY-EYE overlay panel on the right side of the screen is NOT something you should click on.
- If your previous click went to the wrong place (check conversation history), RECALCULATE using the grid.

**3. APP SWITCHING (intent: "act")**
When the user says "switch to Discord", "go to Chrome", "open Discord" (and it might already be running):
- Use {"type": "switch", "target": "discord"} to bring an already-running app to the foreground.
- If the app is not running, the system will automatically launch it.
- Use "switch" when the user says: "switch to", "go to", "show me", "bring up", "focus on", "open" (for common apps).
- Use "launch" ONLY when the user explicitly wants to start a NEW instance.

**4. CONTENT CREATION (intent: "act")**
When the user asks you to write/compose/draft/create text:
- Generate the FULL content yourself.
- Use {"type": "type", "text": "your complete generated text here"} to paste it.
- If a text editor is visible, type directly. Otherwise, click the text area first.
- For "search and draft" requests: use the web search results to compose a detailed, well-written message, then type it.
- NEVER just say you'll write it — actually generate and type the content.

**5. MESSAGING (intent: "act")**
When the user says "send a message to X on Discord" or "type hello in the chat":
- First, look at the screenshot and find the message input field (usually at the bottom of the chat).
- Click the message input field at its exact coordinates.
- Then use {"type": "type", "text": "the message content"} to type the message.
- Then press Enter to send: {"type": "hotkey", "keys": ["enter"]}
- Example flow for "send hi to John on Discord":
  1. {"type": "click", "target": "message input", "x": 640, "y": 700}
  2. {"type": "type", "text": "hi"}
  3. {"type": "hotkey", "keys": ["enter"]}

**6. SEARCH + EXPLAIN (intent: "guide")**
When web search results are provided and the user just wants information:
- Read through ALL the search results.
- Synthesize a comprehensive, spoken answer in the "message" field.
- Speak naturally, as if explaining to a friend.

**7. TERMINAL, OS & PROJECT CREATION (intent: "act")**
When the user asks to "create a project", "open Antigravity", or run complex OS commands:
- You are a senior developer. Use the "cmd" action to run PowerShell commands.
- The `cmd` action runs in the agent's project directory. You MUST use ABSOLUTE paths (e.g., `$env:USERPROFILE\\Desktop\\MyFolder`) if the user asks you to create folders on the Desktop!
- **Terminal output is captured!** After your command runs, its stdout/stderr will be injected into your CONVERSATION HISTORY. Set `"status": "in_progress"` so you can check the result and fix any errors.
- For "open Antigravity" or similar tools: if you know the command, run it via `cmd` (e.g. `code .` or `gsd`).
- If you need multiple steps, chain the actions together!
- **PRO TIP FOR RENAMING**: On Windows, context menus don't always have the word "Rename" (sometimes it's just a small icon). To rename a file or folder, ALWAYS use this reliable workflow:
  1. `{"type": "click_text", "text": "YourFolderName"}`
  2. `{"type": "hotkey", "keys": ["f2"]}`
  3. `{"type": "type", "text": "NewName"}`
  4. `{"type": "hotkey", "keys": ["enter"]}`

**8. LEARNING NEW SKILLS (intent: "act")**
When the user asks you to "learn a new skill", "remember how to do this", or "create a workflow":
- Use the "create_skill" action to permanently save a workflow to your memory.
- You must provide a "name" (lowercase, underscores) and "instruction" (the exact steps or prompt to follow next time).
- Example: {"type": "create_skill", "name": "blender_donut", "instruction": "To make a donut in Blender: 1. Shift+A > Mesh > Torus. 2. Tab into Edit Mode. 3. O for Proportional Editing..."}
- Once a skill is learned, it will automatically appear in your context in future conversations.

**9. LOCAL CODEBASE INTEGRATION (intent: "act")**
When asked to read files, examine code, or write scripts:
- Use `list_dir` to view a directory: `{"type": "list_dir", "path": "src"}`
- Use `read_file` to read contents: `{"type": "read_file", "path": "main.py"}`
- Use `write_file` to write code: `{"type": "write_file", "path": "hello.py", "content": "print('hi')"}`
- If you read a file, the contents will be injected into your CONVERSATION HISTORY on the next loop iteration. ALWAYS set `"status": "in_progress"` if you are waiting to read the output!

**10. CROSS-APP DATA EXTRACTION (RPA) (intent: "act")**
When asked to read an email, extract text, or move data from one app to another:
- First, highlight the target text using `click` or `scroll`.
- Next, use the `{"type": "extract_clipboard"}` action. This will automatically press Ctrl+C and inject the copied data directly into your conversation history!
- Set `"status": "in_progress"` so you can process the extracted data on the next loop iteration and type it into the destination app.

**11. CONTEXTUAL SYSTEM AUDIO (intent: "act")**
When asked to listen to a video, meeting, or audio playing on the desktop:
- Use `{"type": "listen_audio", "duration": 5}` to capture and transcribe the system audio for a specific duration in seconds (max 15s).
- The transcript will be injected into your CONVERSATION HISTORY on the next loop. Set `"status": "in_progress"` to process the transcript!

**12. SCREEN TEXT EXTRACTION (intent: "act")**
When you need to read exact text from the screen (emails, code, error messages) more accurately than vision:
- Use `{"type": "ocr_screen", "x": 0, "y": 0, "w": 800, "h": 600}` to extract text from a screen region.
- The extracted text will appear in your CONVERSATION HISTORY. Set `"status": "in_progress"`!

**13. TEXT-BASED CLICKING (PREFERRED for icons/buttons/labels)**
Instead of guessing pixel coordinates, use:
`{"type": "click_text", "text": "NewFolder", "clicks": 2}`
This finds the text on screen using OCR and clicks it precisely.
USE THIS whenever you can see a text label on the target element.

### CRITICAL JSON RULES:
- Keep ALL text in the "message" and "text" fields on a SINGLE LINE. No line breaks inside strings.
- Use spaces instead of newlines for paragraphs.
- You MUST ALWAYS include the "status" field in your output. If the user's task requires multiple steps, output `"status": "in_progress"`.
- If using `cmd`, ALWAYS use absolute paths AND wrap them in single quotes (e.g., `'C:\\Users\\LENOVO\\Desktop\\AI test'`) to prevent PowerShell space/argument errors.
- **SECURITY**: Some dangerous commands are blocked (format, shutdown, registry edits, downloads). If a command is blocked, you'll see it in your history — find a safe alternative.
- The "message" field is spoken aloud — write it as natural speech.
- Act like a human-like, highly capable assistant. Store memories, refer to past turns if they are in the history.
- **IGNORE STREAM PREVIEWS**: If you see a picture-in-picture window or a recursive screen mirror (like a Discord stream preview), DO NOT click inside it. Always target the actual native UI elements on the main desktop.

### JSON Format:
{
  "intent": "act|guide|ask|ignore",
  "status": "in_progress|complete|failed",
  "message": "Your FULL spoken response. Keep on ONE line. No newlines.",
  "actions": [
    {"type": "click_text", "text": "Submit"},
    {"type": "click_text", "text": "NewFolder", "clicks": 2},
    {"type": "click_text", "text": "NewFolder", "button": "right"},
    {"type": "click", "target": "element", "x": 123, "y": 456},
    {"type": "click", "target": "context menu", "x": 123, "y": 456, "button": "right"},
    {"type": "click", "target": "open file", "x": 123, "y": 456, "clicks": 2},
    {"type": "drag", "x1": 100, "y1": 200, "x2": 400, "y2": 300},
    {"type": "type", "text": "Text content on one line"},
    {"type": "hotkey", "keys": ["enter"]},
    {"type": "launch", "target": "notepad"},
    {"type": "switch", "target": "discord"},
    {"type": "open_url", "url": "https://google.com"},
    {"type": "cmd", "command": "mkdir 'C:\\Users\\LENOVO\\Desktop\\MyFolder'"},
    {"type": "create_skill", "name": "my_skill", "instruction": "Step-by-step instructions"},
    {"type": "read_file", "path": "app.py"},
    {"type": "list_dir", "path": "."},
    {"type": "write_file", "path": "app.py", "content": "print('hello')"},
    {"type": "extract_clipboard"},
    {"type": "listen_audio", "duration": 10},
    {"type": "ocr_screen", "x": 0, "y": 0, "w": 800, "h": 600},
    {"type": "scroll", "amount": -5}
  ],
  "confidence": 0.0-1.0
}"""


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
        """Capture the entire desktop, overlay a coordinate grid, and return as base64 string."""
        try:
            with mss.mss() as sct:
                # Monitor 0 is the full desktop (all monitors combined)
                monitor = sct.monitors[0]
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                # Resize for performance while keeping enough detail for coordinates
                max_w = 1920
                if img.width > max_w:
                    ratio = max_w / img.width
                    img = img.resize((max_w, int(img.height * ratio)), Image.Resampling.LANCZOS)
                
                # Store dimensions for coordinate scaling
                self._desktop_size = (screenshot.width, screenshot.height)
                self._desktop_offset = (monitor["left"], monitor["top"])
                self._img_size = (img.width, img.height)
                
                # Draw coordinate grid overlay to help AI with spatial accuracy
                img = self._draw_grid(img)
                
                # Save debug image (with grid)
                if save_debug:
                    ts = int(time.time())
                    img.save(os.path.join(self.debug_dir, f"vision_{ts}.jpg"), quality=60)
                
                # Convert to base64
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=75)
                return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            logger.logger.error(f"Screen capture failed: {e}")
            return None

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
        """Scale coordinates from the AI's resized image back to the physical desktop space."""
        if not hasattr(self, '_desktop_size') or not hasattr(self, '_img_size'):
            return response
        
        # Use the actual MSS desktop pixel dimensions for scaling
        # MSS gives us the true physical resolution, matching pyautogui's coordinate space
        desk_w, desk_h = self._desktop_size
        img_w, img_h = self._img_size
        
        scale_x = desk_w / img_w
        scale_y = desk_h / img_h
        
        actions = response.get("actions", [])
        for action in actions:
            if "x" in action and "y" in action:
                raw_x = action["x"]
                raw_y = action["y"]
                abs_x = int(raw_x * scale_x)
                abs_y = int(raw_y * scale_y)
                # Clamp to screen bounds with 10px safety margin
                abs_x = max(10, min(desk_w - 10, abs_x))
                abs_y = max(10, min(desk_h - 10, abs_y))
                action["x"] = abs_x
                action["y"] = abs_y
                logger.logger.info(f"Brain: Scaled ({raw_x},{raw_y}) -> ({abs_x},{abs_y}) [img:{img_w}x{img_h} desk:{desk_w}x{desk_h}]")
        
        return response

    def on_voice_input(self, text):
        self._loop_count = 0  # Reset loop counter on new user input
        logger.log_event("BRAIN_VOICE_INPUT", {"text": text})
        self.on_ai_triggered({
            "type": "VOICE_COMMAND",
            "confidence": 1.0,
            "text": text
        })

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
            
            screen_b64 = self._capture_screen_b64()
            
            if screen_b64:
                history_str = short_term_memory.get_history_string()
                skills_str = skill_manager.get_all_skills_context()
                
                prompt = f"""{VISION_SYSTEM_PROMPT}

DESKTOP RESOLUTION: {self._desktop_size[0]}x{self._desktop_size[1]}
PROCESSED IMAGE SIZE: {self._img_size[0]}x{self._img_size[1]}
ACTIVE WINDOW: {state.window}
ACTIVE APP: {state.app}
{web_context}
{skills_str}
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
                    import time
                    tts_done = threading.Event()
                    
                    def _on_tts_finished(data):
                        tts_done.set()
                    
                    bus.subscribe("TTS_FINISHED", _on_tts_finished)
                    
                    # Wait for TTS to finish, but timeout after 10s as safety net
                    if not tts_done.wait(timeout=10.0):
                        logger.logger.warning("Brain: TTS timeout, proceeding with actions")
                    
                    # Small buffer for audio playback to fully stop
                    time.sleep(0.3)
                    bus.publish("ACTION_REQUESTED", response)
                threading.Thread(target=_dispatch, daemon=True).start()
                
            logger.log_event("BRAIN_DECISION", response)
        else:
            bus.publish("SAFE_NO_ACTION")

brain = Brain()
