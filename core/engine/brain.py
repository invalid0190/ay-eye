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
from core.utils.logger import logger


VISION_SYSTEM_PROMPT = """You are ay-eye, a powerful desktop AI assistant. You can SEE the user's full desktop via the attached screenshot.

When the user gives a voice command, analyze the screen and respond with precise actions.

IMPORTANT RULES:
- Identify the EXACT pixel coordinates (x, y) for clicks.
- The screenshot resolution is provided. Use it for accuracy.
- Coordinates (0,0) are the TOP-LEFT of the primary monitor.
- If the user has multiple monitors, the screenshot covers the ENTIRE desktop space.
- Be extremely precise. Zoom in mentally on buttons, icons, and text fields.
- SAFETY: Avoid clicking the exact corners (0,0) or (max, max). Stay at least 20px away from the absolute edges if possible.
- If you need to type, provide the "type" action with the exact text.
- Use "hotkey" for keyboard shortcuts (e.g. ["alt", "f4"] to close windows, ["win", "r"] to run).
- Use "launch" to start applications (e.g. "notepad", "chrome").
- Use "scroll" with an "amount" (positive for up, negative for down).
- CLARITY: If you see multiple similar buttons, choose the most likely one based on context.

Return ONLY valid JSON:
{
  "intent": "act|guide|ask|ignore",
  "message": "Verbal response to user (e.g. 'Opening Discord for you')",
  "actions": [
    {"type": "click", "target": "describe target", "x": 123, "y": 456},
    {"type": "type", "text": "text to type"},
    {"type": "hotkey", "keys": ["ctrl", "c"]},
    {"type": "launch", "target": "app_name"},
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
            screen_b64 = self._capture_screen_b64()
            
            if screen_b64:
                prompt = f"""{VISION_SYSTEM_PROMPT}

DESKTOP RESOLUTION: {self._desktop_size[0]}x{self._desktop_size[1]}
PROCESSED IMAGE SIZE: {self._img_size[0]}x{self._img_size[1]}
ACTIVE WINDOW: {state.window}
ACTIVE APP: {state.app}

USER VOICE COMMAND: "{voice_text}"

Analyze the screenshot and perform the requested actions."""
                
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
            short_term_memory.add({"response": response})
            bus.publish("BRAIN_RESPONDED", response)
            
            if response.get("intent") == "act":
                # Small delay to let TTS start speaking before action
                def _dispatch():
                    import threading # Inline failsafe
                    import time
                    time.sleep(0.6)
                    bus.publish("ACTION_REQUESTED", response)
                threading.Thread(target=_dispatch, daemon=True).start()
                
            logger.log_event("BRAIN_DECISION", response)
        else:
            bus.publish("SAFE_NO_ACTION")

brain = Brain()
