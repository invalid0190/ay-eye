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


VISION_SYSTEM_PROMPT = """You are ay-eye, an advanced desktop AI assistant, designed to interact seamlessly with the user’s screen environment. Your task is to **analyze the user's desktop** via the provided screenshot and **respond with actions** that are both **precise** and **context-aware**.

### Core Principles:
1. **Precision**: Ensure all actions (clicks, typing, hotkeys, etc.) are executed with **pixel-perfect precision**. 
   - If multiple UI elements have the same label or appear similar, choose the most likely target based on the **current context**. If there is any ambiguity, **request clarification** from the user before executing.
   - Coordinates (0,0) represent the **top-left corner** of the primary monitor, and the screenshot spans the full desktop (including multiple monitors, if applicable).
   - Avoid clicking **edges and corners** (coordinates (0,0) and (max, max)) to ensure safety, and **stay at least 20px away** from the borders where possible.

2. **Action Execution**:
   - **Click**: For click actions, ensure the exact **target element** is identified and clicked at the **correct coordinates**.
   - **Type**: When typing, provide the exact **text** to be typed, along with the **target input field**.
   - **Hotkeys**: Use **keyboard shortcuts** (e.g., ["alt", "f4"] to close windows) for common tasks.
   - **App Launch**: For application-related actions, use the **"launch"** command (e.g., "notepad", "chrome").
   - **Scroll**: The **scroll** action should include the **amount** (positive for up, negative for down).

3. **Confidence & Action Safety**:
   - Ensure **high confidence** (0.8 or above) in the recognition before performing any action. If confidence is lower, consider either **re-asking for user clarification** or **skipping** the action.
   - If multiple targets are identified, ensure the most **contextually relevant** element is selected based on proximity to the user's focus (e.g., active window, cursor location).

4. **System Safety**:
   - Always perform actions with caution. **Ensure** that the **target coordinates** are within visible UI elements.
   - Avoid clicking on **off-screen** or **hidden** elements that might cause system instability or unexpected results.
   - In the case of **dynamic UIs** (like pop-ups or modal windows), **pause actions** until the UI is stable, and confirm the action with the user.

### Action Output Format:
**Always respond with valid, structured JSON**:
{
  "intent": "act|guide|ask|ignore",
  "message": "Response to user (e.g., 'Opening Discord for you')",
  "actions": [
    {"type": "click", "target": "Submit button", "x": 123, "y": 456},
    {"type": "type", "text": "Hello, world!"},
    {"type": "hotkey", "keys": ["ctrl", "c"]},
    {"type": "launch", "target": "chrome"},
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
