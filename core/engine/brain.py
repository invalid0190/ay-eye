import base64
import io
import json
import mss
import os
import re
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

_INFO_GATHERING_TERMS = (
    "check", "dekho", "dekh", "bata", "kya", "what", "which", "who",
    "latest", "last", "recent",
    "find", "search", "look up", "read", "review", "inspect", "summarize",
    "status", "compare", "details", "history",
)

_DATA_CAPTURE_ACTIONS = {
    "cmd", "read_file", "list_dir", "ocr_screen", "extract_clipboard", "listen_audio",
}

_NAVIGATION_ACTIONS = {
    "open_url", "switch", "launch", "click", "click_text", "scroll", "hotkey",
}

_INTERMEDIATE_INFO_ACTIONS = _NAVIGATION_ACTIONS | _DATA_CAPTURE_ACTIONS

_BLENDER_CLICK_TYPES = {"click", "click_text", "drag"}

_BLENDER_CONTEXT_TERMS = (
    "blender", "bpy", "blend", "viewport", "sollumz", "fivem", "gta", "mlo",
    "codewalker", "ydr", "ydd", "ybn", "ytyp", "ymap", "mcp", "bridge",
    "server", "localhost",
)

_BLENDER_CREATIVE_TERMS = (
    "create", "make", "model", "build", "design", "recreate", "generate",
    "bana", "banao", "banado", "jaisa", "aisi", "aisa", "like this",
    "something like", "somthing like", "set up", "setup", "setting up",
)

_BLENDER_ENHANCE_TERMS = (
    "enhance", "improve", "detail", "details", "detailing", "professional",
    "polish", "upgrade", "fix detail", "make better", "more detail",
    "aur detail", "aur details", "theek", "quality", "complete",
)

_BLENDER_REFERENCE_TERMS = (
    "image", "picture", "photo", "reference", "visible", "this", "ye", "iss",
    "container", "cafe", "coffee", "shop", "building", "scene", "model",
    "object", "interior", "exterior", "mlo", "garage", "house", "home",
    "restaurant", "office", "warehouse", "store", "retail", "club", "bar",
    "motel", "apartment", "room", "portal", "collision",
)

_SOLLUMZ_EXPLICIT_TERMS = (
    "sollumz", "fivem", "gta", "mlo", "codewalker", "ydr", "ydd", "ybn",
    "ytyp", "ymap", "drawable", "archetype", "collision mesh", "portal",
)

_SOLLUMZ_EXPORT_TERMS = (
    "sollumz property", "sollumz properties", "codewalker", "ydr", "ydd",
    "ybn", "ytyp", "ymap", "drawable", "archetype", "export", "final export",
)

VISION_SYSTEM_PROMPT = """## IDENTITY
You are ay-eye, an advanced desktop AI assistant. You SEE the user's screen (screenshot with grid overlay) and HEAR their voice commands. You may also receive WEB SEARCH RESULTS.
You have memory tools: short-term conversation history, RAG guidance, and saved activity memory. If the user asks what you remember, use the provided memory blocks. Do NOT claim you have no memory. If no relevant saved entry is provided, say you do not see a saved record for that time/topic.

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
- plan: REQUIRED when actions >= 3 OR actions contain cmd/write_file/blender_python/blender_create_scene/blender_enhance_scene. Optional otherwise.

## TASK COMPLETION RULES
- If the user asks you to check, read, find, inspect, summarize, or report information, opening a page/app is only the first step. Use status="in_progress" after open_url/switch/launch/click/scroll until you have actually observed the information and answered it.
- For GitHub questions like latest commits, open/navigate as needed, inspect the visible page, then finish with intent="guide", status="complete", actions=[], and the commit details in "message".
- Do not say "done" or "complete" just because a website or app opened. Complete means the user's actual requested answer/action is finished.

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
- blender_bridge_status: {"type": "blender_bridge_status"} -- Ping Blender's MCP add-on bridge at localhost:9876 and Ay-Eye's fallback bridge at 127.0.0.1:8765.
- blender_python: {"type": "blender_python", "script": "import bpy; bpy.ops..."}
- blender_create_scene: {"type": "blender_create_scene", "description": "detailed scene/model request", "reference_summary": "what is visible in the reference image"}
- blender_enhance_scene: {"type": "blender_enhance_scene", "description": "professional detail/refinement request", "reference_summary": "what needs to be improved or matched from the reference"}

## CLICK RULES
- **ALWAYS use click_text** when the target has visible text (buttons, menus, file names, tabs, links).
- Use coordinate click ONLY for textless elements (canvas, color swatches, unlabeled icons).
- For coordinate click, include "target" describing what you're clicking.
- The screenshot has a GRID OVERLAY. Use grid labels to determine x,y coordinates.
- Coordinates are relative to PROCESSED IMAGE SIZE (provided below), NOT desktop resolution.
- Do NOT click the AY-EYE overlay panel on the right side of the screen.
- If click_text fails (you'll see "CLICK_TEXT: Could not find" in history), fall back to coordinate click.

## PLANNING RULES
- Include a "plan" field when: (a) 3+ actions, OR (b) any cmd/write_file/blender_python/blender_create_scene/blender_enhance_scene action.
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
- {"type": "blender_scene_objects"} -- Blender bridge reported created scene objects
- {"type": "none"} -- skip verification
ALWAYS add expect for cmd, write_file, blender_python, blender_create_scene, and blender_enhance_scene actions. Use blender_scene_objects for blender_create_scene and blender_enhance_scene.

## SAFETY RULES
- Dangerous commands (format, shutdown, rm -rf, registry edits) are blocked. Find safe alternatives.
- If a banking/payment/password window is active, type/click/cmd actions will be blocked.
- If a command was blocked, you'll see it in history. Adapt your approach.
- When reading files or running commands, set status="in_progress" so you can check the output.

## APP-SPECIFIC RULES
Blender: Use Blender API actions/hotkeys, NOT clicks. Blender UI is OpenGL/custom-rendered, so click_text and coordinate clicks are unreliable. Splash screen or open menu: press Escape. Clear/delete all objects: use blender_python with bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(). For "create/model/build/recreate/design something like this/image/reference" requests, do not ask for exact dimensions first; treat each request/image as a fresh subject, ignore older Blender scene memories unless the user explicitly says to reuse them, describe the visible reference in reference_summary with shape, materials, colors, openings, signage, room layout, major props, and style cues, then use blender_create_scene with status="in_progress". For "add details/make it professional/improve/enhance/fix detailing" on an existing Blender scene, use blender_enhance_scene with status="in_progress"; do not rebuild blindly unless the user asks to start over. For MLO blockout requests, use blender_create_scene; it can generate template rooms, portals, collision helpers, and interior props. Use blender_enhance_scene to add polish and verify room/portal/collision evidence on an existing MLO. Only use raw Sollumz/export operations when the user explicitly asks for final YMAP/YTYP/YBN/YDR export or Sollumz property editing. For "MCP server", "bridge", or "is Blender connected" questions, use blender_bridge_status with status="in_progress"; Blender's MCP add-on normally runs on localhost:9876, and Ay-Eye also has a fallback bridge on 127.0.0.1:8765. Do not claim a Blender model is created unless the Blender API result reports success and scene objects.
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

Example 6 -- Info-gathering navigation must continue:
{"intent": "act", "status": "in_progress", "message": "Opening the repository so I can check the latest commits.", "actions": [{"type": "open_url", "url": "https://github.com/owner/repo/commits"}], "confidence": 0.9}
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

    def _answer_blender_bridge_status_from_memory(self, original_task):
        task_text = str(original_task or "").lower()
        if "blender" not in task_text or not any(term in task_text for term in ("mcp", "bridge", "server", "connected", "connection")):
            return False

        history = short_term_memory.get_history_string()
        matches = re.findall(r"BLENDER_BRIDGE_STATUS \[(CONNECTED|NOT_CONNECTED)\]:(.*)", history)
        if not matches:
            return False

        status, detail = matches[-1]
        self._loop_count = 0
        message = (
            f"Blender MCP check complete: {detail.strip()}"
            if status == "CONNECTED"
            else f"Blender bridge check complete: not connected. {detail.strip()}"
        )
        bus.publish("BRAIN_RESPONDED", {
            "intent": "guide",
            "status": "complete" if status == "CONNECTED" else "failed",
            "message": message[:500],
            "actions": [],
            "confidence": 1.0,
        })
        return True

    def on_verification_loop(self, data):
        original_task = (
            data.get("source_user_text")
            or data.get("original_task")
            or data.get("user_command")
            or "the user's original task"
        )
        if self._answer_blender_bridge_status_from_memory(original_task):
            return

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
            "original_task": original_task,
            "text": f"SYSTEM INSTRUCTION: You are in autonomous loop iteration {self._loop_count}/{self.MAX_LOOP_ITERATIONS}. Original user task: {original_task}. Look at the screen to verify if your previous actions succeeded. If the original task is finished, answer the user with intent='guide', status='complete', and actions=[]. If more steps are needed, set status='in_progress' and provide the next actions. Opening or focusing a page is not enough for information-gathering tasks; inspect the visible content and report the requested information."
        })

    def _capture_screen_b64(self, save_debug=True):
        """Get latest frame from live perception and add grid."""
        prepare_started = time.time()
        try:
            bus.publish("VISION_CAPTURE_PREPARE", {"reason": "hide_ayeye_chrome"})
        except Exception:
            pass
        time.sleep(0.25)

        b64, frame = live_perception.get_latest_frame_b64()
        if frame and getattr(frame, "timestamp", 0) < prepare_started:
            deadline = time.time() + 0.6
            while time.time() < deadline:
                time.sleep(0.05)
                b64, frame = live_perception.get_latest_frame_b64()
                if frame and getattr(frame, "timestamp", 0) >= prepare_started:
                    break
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

    def _force_followup_for_unfinished_info_task(self, response, original_task):
        """Keep research/check tasks alive when the model only navigated."""
        if not isinstance(response, dict) or not original_task:
            return response
        if response.get("intent") != "act" or response.get("status") != "complete":
            return response

        actions = response.get("actions") or []
        if not actions:
            return response

        task_text = str(original_task).lower()
        if not any(term in task_text for term in _INFO_GATHERING_TERMS):
            return response

        action_types = {a.get("type") for a in actions if isinstance(a, dict)}
        if not action_types or not action_types.issubset(_INTERMEDIATE_INFO_ACTIONS):
            return response

        response = dict(response)
        response["status"] = "in_progress"
        response["message"] = (
            response.get("message")
            or "I opened it; now I'll inspect the page and finish the task."
        )
        logger.log_event("BRAIN_STATUS_FORCED_IN_PROGRESS", {
            "reason": "info_task_after_navigation",
            "original_task": str(original_task)[:160],
            "actions": list(action_types),
        })
        return response

    @staticmethod
    def _is_blender_state(state):
        active_app = (getattr(state, "app", "") or "").lower()
        active_window = (getattr(state, "window", "") or "").lower()
        return "blender" in active_app or "blender" in active_window

    @staticmethod
    def _contains_any(text, terms):
        return any(term in text for term in terms)

    def _looks_like_blender_task(self, response, original_task, state):
        if self._is_blender_state(state):
            return True

        try:
            action_text = json.dumps(response.get("actions") or [], ensure_ascii=False)
        except Exception:
            action_text = str(response.get("actions") or "")

        combined = f"{original_task or ''} {response.get('message') or ''} {action_text}".lower()
        return self._contains_any(combined, _BLENDER_CONTEXT_TERMS)

    def _normalize_blender_task(self, response, original_task, state):
        """Rewrite common Blender UI tasks away from fragile screen clicks."""
        if not isinstance(response, dict) or not original_task:
            return response
        if not self._looks_like_blender_task(response, original_task, state):
            return response

        task_text = str(original_task).lower()
        response_text = str(response.get("message") or "").lower()
        existing_actions = response.get("actions") or []
        try:
            action_text = json.dumps(existing_actions, ensure_ascii=False).lower()
        except Exception:
            action_text = str(existing_actions).lower()
        combined_text = f"{task_text} {response_text} {action_text}"
        action_types = {a.get("type") for a in existing_actions if isinstance(a, dict)}
        explicit_sollumz = self._contains_any(task_text, _SOLLUMZ_EXPORT_TERMS)
        unwanted_sollumz_plan = (
            not explicit_sollumz
            and self._contains_any(f"{response_text} {action_text}", _SOLLUMZ_EXPLICIT_TERMS)
            and self._contains_any(combined_text, ("container", "cafe", "coffee", "shop", "building", "scene", "model"))
        )
        wants_splash_close = any(term in task_text for term in (
            "splash", "welcome", "startup screen", "close screen", "close karo", "band karo",
        ))
        wants_delete_all = any(term in task_text for term in (
            "delete", "remove", "clear", "clean", "sab", "everything", "all object", "all objects",
            "cube", "x se", "x press",
        ))
        wants_bridge_status = (
            "blender" in combined_text
            and self._contains_any(combined_text, ("mcp", "bridge", "server", "connected", "connection", "opened through"))
            and not self._contains_any(combined_text, _BLENDER_CREATIVE_TERMS)
        )
        creation_terms_for_new_scene = (
            "create", "model", "build", "design", "recreate", "generate",
            "bana", "banao", "banado", "something like", "somthing like",
        )
        wants_enhance_scene = (
            not explicit_sollumz
            and self._contains_any(combined_text, _BLENDER_ENHANCE_TERMS)
            and self._contains_any(combined_text, _BLENDER_REFERENCE_TERMS)
            and not self._contains_any(task_text, creation_terms_for_new_scene)
        )
        wants_scene_create = (
            not explicit_sollumz
            and (
                (
                    self._contains_any(combined_text, _BLENDER_CREATIVE_TERMS)
                    and self._contains_any(combined_text, _BLENDER_REFERENCE_TERMS)
                )
                or unwanted_sollumz_plan
            )
        )
        has_fragile_blender_clicks = bool(action_types & _BLENDER_CLICK_TYPES)

        if wants_bridge_status:
            normalized = dict(response)
            normalized["intent"] = "act"
            normalized["status"] = "in_progress"
            normalized["message"] = "I'll check Ay-Eye's local Blender bridge connection directly."
            normalized["actions"] = [{
                "type": "blender_bridge_status",
                "expect": {"type": "none"},
            }]
            normalized["plan"] = [
                "Ping the local MCP-style Blender bridge and read the returned scene summary.",
            ]
            normalized["confidence"] = max(float(normalized.get("confidence", 0.0) or 0.0), 0.9)
            logger.log_event("BRAIN_BLENDER_BRIDGE_STATUS_NORMALIZED", {
                "original_task": str(original_task)[:160],
            })
            return normalized

        if wants_enhance_scene:
            enhance_description = (
                f"{original_task}. Enhance the existing Blender scene non-destructively. "
                "Add professional detail, material cleanup, bevels, labels, lighting, camera framing, "
                "and if this is an MLO, verify room volume guides, portal guides, and collision proxy guides."
            )
            reference_summary = " ".join(
                part for part in (str(response.get("message") or ""), str(original_task)) if part
            )[:500]

            normalized = dict(response)
            normalized["intent"] = "act"
            normalized["status"] = "in_progress"
            normalized["message"] = "I'll refine the existing Blender scene and verify the detail pass through the bridge."
            normalized["actions"] = [
                {
                    "type": "hotkey",
                    "keys": ["escape"],
                    "expect": {"type": "none"},
                },
                {
                    "type": "blender_enhance_scene",
                    "description": enhance_description,
                    "reference_summary": reference_summary,
                    "expect": {"type": "blender_scene_objects"},
                },
            ]
            normalized["plan"] = [
                "Close any Blender splash or modal with Escape.",
                "Use Blender enhancement to preserve the current scene while adding professional details, labels, lighting, and MLO evidence.",
            ]
            normalized["confidence"] = max(float(normalized.get("confidence", 0.0) or 0.0), 0.9)
            logger.log_event("BRAIN_BLENDER_ENHANCE_NORMALIZED", {
                "original_task": str(original_task)[:160],
                "actions": ["hotkey", "blender_enhance_scene"],
            })
            return normalized

        if wants_scene_create:
            scene_description = (
                f"{original_task}. Create a detailed Blender scene from the user's current request and reference only. "
                "Do not reuse an old scene template unless the user explicitly asks for that subject. "
                "Match the described object type, silhouette, materials, colors, openings, props, layout, labels, lighting, and camera."
            )
            reference_summary = " ".join(
                part for part in (str(response.get("message") or ""), str(original_task)) if part
            )[:500]

            if "blender_create_scene" in action_types:
                normalized = dict(response)
                normalized_actions = []
                for action in existing_actions:
                    if isinstance(action, dict) and action.get("type") == "blender_create_scene":
                        action = dict(action)
                        action.setdefault("description", scene_description)
                        action.setdefault("reference_summary", reference_summary)
                        if (action.get("expect") or {}).get("type") in (None, "none"):
                            action["expect"] = {"type": "blender_scene_objects"}
                    normalized_actions.append(action)
                normalized["actions"] = normalized_actions
                normalized["intent"] = "act"
                normalized["status"] = "in_progress"
                normalized["plan"] = normalized.get("plan") or [
                    "Close any Blender splash or modal if it blocks the viewport.",
                    "Use Blender scene creation to build a procedural model from the visible reference.",
                ]
                normalized["confidence"] = max(float(normalized.get("confidence", 0.0) or 0.0), 0.9)
                return normalized

            normalized = dict(response)
            normalized["intent"] = "act"
            normalized["status"] = "in_progress"
            normalized["message"] = (
                "I'll create a first-pass Blender scene from the visible reference instead of asking for more specs."
            )
            normalized["actions"] = [
                {
                    "type": "hotkey",
                    "keys": ["escape"],
                    "expect": {"type": "none"},
                },
                {
                    "type": "blender_create_scene",
                    "description": scene_description,
                    "reference_summary": reference_summary,
                    "expect": {"type": "blender_scene_objects"},
                },
            ]
            normalized["plan"] = [
                "Close any Blender splash or modal with Escape.",
                "Use Blender scene creation to generate the reference-inspired model with materials, lights, camera, and details.",
            ]
            normalized["confidence"] = max(float(normalized.get("confidence", 0.0) or 0.0), 0.9)
            logger.log_event("BRAIN_BLENDER_SCENE_NORMALIZED", {
                "original_task": str(original_task)[:160],
                "actions": ["hotkey", "blender_create_scene"],
            })
            return normalized

        if not wants_splash_close and not wants_delete_all and not has_fragile_blender_clicks:
            return response
        if wants_delete_all and "blender_python" in action_types:
            return response

        actions = []
        plan = []

        if wants_splash_close:
            actions.append({
                "type": "hotkey",
                "keys": ["escape"],
                "expect": {"type": "none"},
            })
            plan.append("Close Blender's splash screen with Escape.")

        if wants_delete_all:
            actions.append({
                "type": "blender_python",
                "description": "delete all Blender scene objects",
                "script": (
                    "import bpy\n"
                    "bpy.ops.object.select_all(action='SELECT')\n"
                    "bpy.ops.object.delete()\n"
                    "print('AYEYE_SCENE_CLEARED: deleted all objects')"
                ),
                "expect": {"type": "none"},
            })
            plan.append("Use Blender Python to select and delete all scene objects.")

        if not actions:
            actions.append({
                "type": "hotkey",
                "keys": ["escape"],
                "expect": {"type": "none"},
            })
            plan.append("Avoid fragile Blender UI clicking and use a keyboard/API action instead.")

        normalized = dict(response)
        normalized["intent"] = "act"
        normalized["status"] = "in_progress" if wants_delete_all else "complete"
        normalized["message"] = (
            "Blender UI clicks are unreliable here, so I'll use Escape and Blender Python instead."
            if wants_delete_all
            else "Closing the Blender splash screen with Escape."
        )
        normalized["actions"] = actions
        normalized["plan"] = plan
        normalized["confidence"] = max(float(normalized.get("confidence", 0.0) or 0.0), 0.9)
        logger.log_event("BRAIN_BLENDER_ACTION_NORMALIZED", {
            "original_task": str(original_task)[:160],
            "actions": [a.get("type") for a in actions],
        })
        return normalized

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
        original_task = trigger_data.get("original_task") or voice_text
        
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
                
                # App-aware context injection
                app_context = ""
                active_app = (state.app or "").lower()
                active_window = (state.window or "").lower()
                skills_str = skill_manager.get_all_skills_context(
                    voice_text,
                    active_app=active_app,
                    active_window=active_window,
                )
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
For Blender menu/import/model operations, use blender_open_import_menu, blender_import_file, blender_create_scene, blender_enhance_scene, or blender_python with status=in_progress so you can verify after the API action. For reference image creative requests, use blender_create_scene and put a dense visual analysis in reference_summary: object type, silhouette, materials, colors, openings, signage/text, room layout, props, style, and visible proportions. Treat every new image/request as a fresh subject and do not carry over an old container cafe, MLO, or any previous Blender scene unless the user asks to continue that scene. For existing-scene refinement requests like "add details", "make professional", "improve", or "fix detailing", use blender_enhance_scene and preserve the current scene. For MLO blockouts, use blender_create_scene for room/portal/collision helper generation, then blender_enhance_scene for polish/detail passes; reserve raw Sollumz/export scripts for final export or explicit property-editing requests. For MCP/server/bridge connection questions, use blender_bridge_status; Blender's MCP add-on runs on localhost:9876 when enabled, and Ay-Eye has a fallback bridge on 127.0.0.1:8765. Do NOT use click_text, and do not claim a Blender model/menu was created/opened unless the Blender API result reports success with scene objects or you verified it on screen.
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

                activity_context = ""
                try:
                    activity_context = rag_manager.build_activity_context(voice_text)
                except Exception as _activity_err:
                    logger.logger.error(f"RAG: activity context failed, continuing without it: {_activity_err}")
                
                prompt = f"""{VISION_SYSTEM_PROMPT}

IMPORTANT: Return coordinates relative to the PROCESSED IMAGE SIZE you are seeing, not the desktop resolution. Ay-Eye's own panel is hidden during capture/action, so do not compensate for where it used to be.

DESKTOP RAW SIZE: {frame.raw_size[0]}x{frame.raw_size[1]}
PROCESSED IMAGE SIZE: {frame.processed_size[0]}x{frame.processed_size[1]}
DESKTOP OFFSET: {frame.desktop_offset[0]}, {frame.desktop_offset[1]}
ACTIVE WINDOW: {state.window}
ACTIVE APP: {state.app}
{app_context}
{web_context}
{rag_context}
{activity_context}
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
            response = self._normalize_blender_task(response, original_task, state)
            response = self._force_followup_for_unfinished_info_task(response, original_task)
            if original_task:
                response["source_user_text"] = original_task
                if isinstance(response.get("actions"), list):
                    for action in response["actions"]:
                        if isinstance(action, dict):
                            action.setdefault("source_user_text", original_task)

        mode = decision_engine.get_response_mode(response.get("confidence", 0))
        response["mode"] = mode
        
        if mode != "IGNORE":
            memory_manager.store(state.app, str(state.window), response)
            if is_voice and voice_text:
                memory_user_text = original_task if str(voice_text).startswith("SYSTEM INSTRUCTION:") else voice_text
                short_term_memory.add(memory_user_text, response)
                try:
                    rag_manager.remember_interaction(memory_user_text, response, state.app, state.window)
                except Exception as _remember_err:
                    logger.logger.error(f"RAG: remember_interaction failed: {_remember_err}")
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
