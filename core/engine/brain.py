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
- Identify exact pixel coordinates from the screenshot.
- Use precise actions: click, type, hotkey, launch, switch, scroll.
- Coordinates (0,0) = top-left. Stay 20px from edges.
- Keep the "message" field as a short verbal confirmation of what you're doing.

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
- For "create a project": use `cmd` to create folders or initialize it.
- For "open Antigravity" or similar tools: if you know the command, run it via `cmd` (e.g. `code .` or `gsd`).
- If you need multiple steps, chain the actions together!

**8. LEARNING NEW SKILLS (intent: "act")**
When the user asks you to "learn a new skill", "remember how to do this", or "create a workflow":
- Use the "create_skill" action to permanently save a workflow to your memory.
- You must provide a "name" (lowercase, underscores) and "instruction" (the exact steps or prompt to follow next time).
- Example: {"type": "create_skill", "name": "blender_donut", "instruction": "To make a donut in Blender: 1. Shift+A > Mesh > Torus. 2. Tab into Edit Mode. 3. O for Proportional Editing..."}
- Once a skill is learned, it will automatically appear in your context in future conversations.

### CRITICAL JSON RULES:
- Keep ALL text in the "message" and "text" fields on a SINGLE LINE. No line breaks inside strings.
- Use spaces instead of newlines for paragraphs.
- The "message" field is spoken aloud — write it as natural speech.
- Act like a human-like, highly capable assistant. Store memories, refer to past turns if they are in the history.

### JSON Format:
{
  "intent": "act|guide|ask|ignore",
  "message": "Your FULL spoken response. Keep on ONE line. No newlines.",
  "actions": [
    {"type": "click", "target": "element", "x": 123, "y": 456},
    {"type": "type", "text": "Text content on one line"},
    {"type": "hotkey", "keys": ["enter"]},
    {"type": "launch", "target": "notepad"},
    {"type": "switch", "target": "discord"},
    {"type": "cmd", "command": "mkdir my_project; cd my_project; npm init -y"},
    {"type": "create_skill", "name": "my_skill", "instruction": "Step-by-step instructions to remember"},
    {"type": "scroll", "amount": -5}
  ],
  "confidence": 0.0-1.0
}"""


class Brain:
    def __init__(self):
        bus.subscribe("AI_TRIGGERED", self.on_ai_triggered)
        bus.subscribe("VOICE_INPUT_RECEIVED", self.on_voice_input)
        self.debug_dir = os.path.join(os.getcwd(), "analytics", "vision_debug")
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir, exist_ok=True)

    def _capture_screen_b64(self, save_debug=True):
        """Capture the entire desktop and return as base64 string."""
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
                
                # Save debug image
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

    def _scale_coords(self, response):
        """Scale coordinates from resized image back to desktop pixels."""
        if not hasattr(self, '_desktop_size') or not hasattr(self, '_img_size'):
            return response
        
        scale_x = self._desktop_size[0] / self._img_size[0]
        scale_y = self._desktop_size[1] / self._img_size[1]
        
        actions = response.get("actions", [])
        for action in actions:
            if "x" in action and "y" in action:
                # Scale and add offset (to handle multi-monitor coordinate space)
                abs_x = int(action["x"] * scale_x) + self._desktop_offset[0]
                abs_y = int(action["y"] * scale_y) + self._desktop_offset[1]
                action["x"] = abs_x
                action["y"] = abs_y
        
        return response

    def on_voice_input(self, text):
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
                # Wait for TTS to announce the plan before executing actions
                def _dispatch():
                    import time
                    # Give TTS time to speak the confirmation message
                    msg_len = len(response.get("message", ""))
                    # Estimate: ~100ms per character of speech, minimum 2s
                    wait_time = max(2.0, min(msg_len * 0.08, 6.0))
                    time.sleep(wait_time)
                    bus.publish("ACTION_REQUESTED", response)
                threading.Thread(target=_dispatch, daemon=True).start()
                
            logger.log_event("BRAIN_DECISION", response)
        else:
            bus.publish("SAFE_NO_ACTION")

brain = Brain()
