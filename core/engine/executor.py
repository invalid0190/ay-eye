import os
import pyautogui
import re
import subprocess
import tempfile
import time
import random
import threading
from core.engine.event_bus import bus
from core.engine.action_state import action_state
from core.engine.window_manager import window_manager
from core.utils.logger import logger
from core.vision.live_perception import live_perception
from core.vision.screen_locator import screen_locator
from core.rag import rag_manager
from core.engine.blender_bridge import BlenderBridgeClient, BlenderMCPClient, build_bootstrap_script
from core.engine.blender_scene_builder import build_scene_script

_BLENDER_CREATIVE_TERMS = (
    "create", "make", "model", "build", "design", "recreate", "generate",
    "bana", "banao", "banado", "like this", "something like", "somthing like",
    "set up", "setup", "setting up",
)

_BLENDER_SCENE_TERMS = (
    "blender", "scene", "model", "reference", "image", "picture", "photo",
    "container", "cafe", "coffee", "shop", "building", "object", "mlo",
    "interior", "garage", "house", "home", "restaurant", "office",
    "warehouse", "store", "retail", "club", "bar", "motel", "apartment",
    "room", "portal", "collision",
)

_SOLLUMZ_EXPLICIT_TERMS = (
    "sollumz property", "sollumz properties", "codewalker", "ydr", "ydd",
    "ybn", "ytyp", "ymap", "drawable", "archetype", "export", "final export",
)

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

    @staticmethod
    def _contains_any(text, terms):
        return any(term in text for term in terms)

    def _should_redirect_blender_python_to_scene(self, action):
        """Route creative Blender bpy scripts through the verified scene builder."""
        script = str(action.get("script") or "")
        description = str(action.get("description") or "")
        source_text = str(action.get("source_user_text") or "")
        combined = f"{source_text} {description} {script}".lower()
        explicit_sollumz = self._contains_any(source_text.lower(), _SOLLUMZ_EXPLICIT_TERMS)

        if explicit_sollumz:
            return False

        mentions_unwanted_sollumz = (
            self._contains_any(f"{description} {script}".lower(), _SOLLUMZ_EXPLICIT_TERMS)
            and self._contains_any(combined, _BLENDER_SCENE_TERMS)
        )
        looks_like_scene_creation = (
            self._contains_any(combined, _BLENDER_CREATIVE_TERMS)
            and self._contains_any(combined, _BLENDER_SCENE_TERMS)
        )

        if not (mentions_unwanted_sollumz or looks_like_scene_creation):
            return False

        # Keep precise utility scripts like "delete all objects" on the bpy path.
        utility_terms = ("delete all", "clear scene", "select_all", "object.delete", "import_file")
        return not self._contains_any(combined, utility_terms)

    def _run_blender_create_scene(self, description, reference_summary=""):
        try:
            window_manager.switch_to("blender")
            pyautogui.press("escape")
            time.sleep(0.1)
        except Exception:
            pass

        script = build_scene_script(description, reference_summary)
        label = description[:90] or "reference scene"
        return self._send_python_to_blender_console(
            script,
            f"create Blender scene: {label}",
            restore_layout=True,
            timeout=90,
            min_objects=1,
        )

    def _check_blender_bridge_status(self):
        mcp_client = BlenderMCPClient()
        mcp_result = None
        for _attempt in range(3):
            mcp_result = mcp_client.ping(timeout=1.2)
            if mcp_result and mcp_result.get("ok"):
                break
            time.sleep(0.2)
        bridge_client = BlenderBridgeClient()
        bridge_result = bridge_client.ping(timeout=0.6)
        try:
            from core.state.short_term import short_term_memory
            if mcp_result and mcp_result.get("ok"):
                scene = mcp_result.get("scene") or {}
                object_count = scene.get("object_count", -1)
                mesh_count = scene.get("mesh_count", -1)
                names = ", ".join(str(name) for name in (scene.get("object_names") or [])[:12])
                ayeye_state = "connected" if bridge_result and bridge_result.get("ok") else "not_connected"
                short_term_memory.add_system_context(
                    "BLENDER_BRIDGE_STATUS [CONNECTED]: "
                    f"blender_mcp=connected host={mcp_client.host} port={mcp_client.port} "
                    f"object_count={object_count} mesh_count={mesh_count} object_names={names}. "
                    f"ayeye_bridge={ayeye_state} host={bridge_client.host} port={bridge_client.port}"
                )
                logger.log_event("BLENDER_BRIDGE_STATUS", {
                    "status": "CONNECTED",
                    "server": "blender_mcp",
                    "host": mcp_client.host,
                    "port": mcp_client.port,
                    "object_count": object_count,
                    "mesh_count": mesh_count,
                    "ayeye_bridge": ayeye_state,
                })
                return True

            if bridge_result and bridge_result.get("ok"):
                scene = bridge_result.get("scene") or {}
                object_count = scene.get("object_count", -1)
                mesh_count = scene.get("mesh_count", -1)
                names = ", ".join(str(name) for name in (scene.get("object_names") or [])[:12])
                short_term_memory.add_system_context(
                    "BLENDER_BRIDGE_STATUS [CONNECTED]: "
                    f"blender_mcp=not_connected host={mcp_client.host} port={mcp_client.port}. "
                    f"ayeye_bridge=connected host={bridge_client.host} port={bridge_client.port} "
                    f"object_count={object_count} mesh_count={mesh_count} object_names={names}"
                )
                logger.log_event("BLENDER_BRIDGE_STATUS", {
                    "status": "CONNECTED",
                    "server": "ayeye_bridge",
                    "host": bridge_client.host,
                    "port": bridge_client.port,
                    "object_count": object_count,
                    "mesh_count": mesh_count,
                })
                return True

            short_term_memory.add_system_context(
                "BLENDER_BRIDGE_STATUS [NOT_CONNECTED]: "
                f"blender_mcp=not_connected host={mcp_client.host} port={mcp_client.port}. "
                f"ayeye_bridge=not_connected host={bridge_client.host} port={bridge_client.port}"
            )
            logger.log_event("BLENDER_BRIDGE_STATUS", {
                "status": "NOT_CONNECTED",
                "mcp_host": mcp_client.host,
                "mcp_port": mcp_client.port,
                "bridge_host": bridge_client.host,
                "bridge_port": bridge_client.port,
            })
            return True
        except Exception as exc:
            logger.logger.error(f"Executor: Blender bridge status check failed: {exc}")
            return False

    def _resolve_target_point(
        self,
        target,
        frame=None,
        methods=("uia", "ocr"),
        min_confidence=0.62,
        approximate=None,
    ):
        """Resolve a named target through the shared screen locator."""
        result = screen_locator.locate(
            target,
            frame=frame,
            methods=methods,
            min_confidence=min_confidence,
            approximate=approximate,
        )
        if not result:
            return None
        return result.x, result.y

    def _publish_click_highlight(self, x, y, locator_result=None):
        width = 40
        height = 40
        if locator_result and locator_result.bbox:
            width = max(24, min(180, int(locator_result.bbox[2])))
            height = max(24, min(180, int(locator_result.bbox[3])))

        bus.publish("HIGHLIGHT_REQUESTED", {
            "x": int(x),
            "y": int(y),
            "w": width,
            "h": height,
            "method": locator_result.method if locator_result else "coordinate",
            "target": locator_result.target if locator_result else "",
        })

    @staticmethod
    def _point_xy(point):
        if not point:
            return None
        if hasattr(point, "x") and hasattr(point, "y"):
            return int(point.x), int(point.y)
        return int(point[0]), int(point[1])

    def _click_ignore_regions(self, old_cursor, new_cursor, locator_result=None):
        regions = []
        for point in [self._point_xy(old_cursor), self._point_xy(new_cursor)]:
            if not point:
                continue
            x, y = point
            regions.append((x - 96, y - 96, 192, 192))

        if locator_result and locator_result.bbox:
            x, y, w, h = locator_result.bbox
            pad = 36
            regions.append((int(x) - pad, int(y) - pad, int(w) + (pad * 2), int(h) + (pad * 2)))

        return regions

    def _click_at(self, x, y, button, clicks, frame_before, target_name="", locator_result=None):
        jx, jy = self._clamp_point(x, y, frame_before)
        self._publish_click_highlight(jx, jy, locator_result)

        duration = random.uniform(0.12, 0.25)
        pyautogui.moveTo(jx, jy, duration=duration, tween=pyautogui.easeOutQuad)
        time.sleep(0.05)
        pyautogui.click(button=button, clicks=clicks)

        locator_note = ""
        if locator_result:
            locator_note = (
                f" via {locator_result.method} match '{locator_result.label}' "
                f"(confidence={locator_result.confidence:.2f})"
            )

        logger.logger.info(f"Executor: {button}-click x{clicks} at ({jx},{jy}){locator_note}")

        from core.state.short_term import short_term_memory
        short_term_memory.add_system_context(
            f"CLICK_EXECUTED: {button}-click x{clicks} at pixel ({jx},{jy}) "
            f"targeting '{target_name or 'coordinate target'}'{locator_note}"
        )
        return jx, jy

    def _click_with_retry(
        self,
        x,
        y,
        button,
        clicks,
        frame_before,
        target_name="",
        locator_result=None,
        original_point=None,
    ):
        old_cursor = pyautogui.position()
        clicked_x, clicked_y = self._click_at(
            x,
            y,
            button,
            clicks,
            frame_before,
            target_name,
            locator_result,
        )

        time.sleep(0.3)
        ignore_regions = self._click_ignore_regions(old_cursor, (clicked_x, clicked_y), locator_result)
        changed = live_perception.verify_screen_changed(frame_before, ignore_regions=ignore_regions)
        if changed:
            return True

        if button != "left" or clicks != 1 or not target_name or not original_point:
            return False
        if locator_result and locator_result.method == "visual":
            return False

        retry_frame = live_perception.get_latest_frame() or frame_before
        retry_result = screen_locator.locate(
            target_name,
            frame=retry_frame,
            methods=("visual",),
            min_confidence=0.45,
            approximate=original_point,
        )
        if not retry_result:
            return False

        distance = ((retry_result.x - clicked_x) ** 2 + (retry_result.y - clicked_y) ** 2) ** 0.5
        if distance < 6:
            return False

        from core.state.short_term import short_term_memory
        short_term_memory.add_system_context(
            f"CLICK_RETRY: No screen change detected after clicking '{target_name}'. "
            f"Retrying via visual locator at ({retry_result.x}, {retry_result.y})."
        )
        logger.logger.info(
            f"Executor: Retrying click for '{target_name}' via visual locator at "
            f"({retry_result.x},{retry_result.y})"
        )
        old_retry_cursor = pyautogui.position()
        self._click_at(
            retry_result.x,
            retry_result.y,
            button,
            clicks,
            frame_before,
            target_name,
            retry_result,
        )
        time.sleep(0.3)
        retry_ignore_regions = ignore_regions + self._click_ignore_regions(
            old_retry_cursor,
            (retry_result.x, retry_result.y),
            retry_result,
        )
        return live_perception.verify_screen_changed(frame_before, ignore_regions=retry_ignore_regions)

    @staticmethod
    def _indent_script(script):
        return "\n".join(f"    {line}" if line.strip() else "" for line in script.splitlines())

    @staticmethod
    def _scene_count(result):
        after = result.get("after") if isinstance(result, dict) else {}
        if not isinstance(after, dict):
            return -1
        try:
            return int(after.get("object_count", -1))
        except Exception:
            return -1

    @staticmethod
    def _scene_names(result):
        after = result.get("after") if isinstance(result, dict) else {}
        if not isinstance(after, dict):
            return ""
        names = after.get("object_names") or []
        if not isinstance(names, list):
            return ""
        return ", ".join(str(name) for name in names[:12])

    def _record_blender_result(self, status, description, result=None, reason=""):
        try:
            from core.state.short_term import short_term_memory
            if status == "SUCCESS":
                object_count = self._scene_count(result or {})
                names = self._scene_names(result or {})
                stdout = ((result or {}).get("stdout") or "").strip()
                short_term_memory.add_system_context(
                    f"BLENDER_API_RESULT [SUCCESS]: {description}. "
                    f"object_count={object_count}. object_names={names}. stdout={stdout[:1000]}"
                )
            else:
                error = reason or ((result or {}).get("error") or "unknown Blender bridge error")
                object_count = self._scene_count(result or {})
                stdout = ((result or {}).get("stdout") or "").strip()
                short_term_memory.add_system_context(
                    f"BLENDER_API_RESULT [FAILED]: {description}. "
                    f"object_count={object_count}. error={str(error)[:1200]}. stdout={stdout[:1000]}"
                )
        except Exception:
            pass

    def _ensure_blender_bridge(self):
        """Start or verify the local in-Blender execution bridge."""
        client = BlenderBridgeClient()
        if client.ping():
            return client

        bootstrap = build_bootstrap_script()
        if not self._send_python_to_blender_console_raw(
            bootstrap,
            "start Ay-Eye Blender bridge",
            restore_layout=True,
        ):
            self._record_blender_result(
                "FAILED",
                "start Ay-Eye Blender bridge",
                reason="Could not paste bootstrap script into Blender's Python console.",
            )
            return None

        deadline = time.time() + 6.0
        while time.time() < deadline:
            time.sleep(0.25)
            if client.ping(timeout=0.5):
                try:
                    from core.state.short_term import short_term_memory
                    short_term_memory.add_system_context("BLENDER_BRIDGE_RESULT [READY]: Ay-Eye Blender bridge is connected.")
                except Exception:
                    pass
                return client

        self._record_blender_result(
            "FAILED",
            "start Ay-Eye Blender bridge",
            reason="Bridge did not answer on localhost after bootstrap.",
        )
        return None

    def _send_python_to_blender_console(self, script, description="Blender script", restore_layout=True, timeout=60, min_objects=0):
        """Run bpy code in Blender and require a structured bridge result."""
        if not script or not script.strip():
            logger.logger.warning("Executor: Empty Blender Python script")
            return False

        mcp_client = BlenderMCPClient()
        mcp_result = mcp_client.execute(script, description=description, timeout=timeout)
        if mcp_result is not None:
            object_count = self._scene_count(mcp_result)
            if not mcp_result.get("ok"):
                self._record_blender_result("FAILED", description, result=mcp_result)
                logger.logger.warning(f"Executor: Blender MCP action failed: {description}")
                return False
            if min_objects and object_count < min_objects:
                self._record_blender_result(
                    "FAILED",
                    description,
                    result=mcp_result,
                    reason=f"Script completed through Blender MCP but scene has only {object_count} object(s).",
                )
                logger.logger.warning(
                    f"Executor: Blender MCP scene action produced too few objects ({object_count})"
                )
                return False

            self._record_blender_result("SUCCESS", f"{description} via Blender MCP", result=mcp_result)
            logger.logger.info(f"Executor: Blender MCP action succeeded: {description}")
            return True

        client = self._ensure_blender_bridge()
        if not client:
            return False

        try:
            result = client.execute(script, description=description, timeout=timeout)
        except Exception as exc:
            self._record_blender_result("FAILED", description, reason=f"Bridge request failed: {exc}")
            logger.logger.error(f"Executor: Blender bridge request failed: {exc}")
            return False

        object_count = self._scene_count(result)
        if not result.get("ok"):
            self._record_blender_result("FAILED", description, result=result)
            logger.logger.warning(f"Executor: Blender bridge action failed: {description}")
            return False
        if min_objects and object_count < min_objects:
            self._record_blender_result(
                "FAILED",
                description,
                result=result,
                reason=f"Script completed but scene has only {object_count} object(s).",
            )
            logger.logger.warning(
                f"Executor: Blender scene action produced too few objects ({object_count})"
            )
            return False

        self._record_blender_result("SUCCESS", description, result=result)
        logger.logger.info(f"Executor: Blender bridge action succeeded: {description}")
        return True

    def _send_python_to_blender_console_raw(self, script, description="Blender script", restore_layout=True):
        """Paste bootstrap code into Blender's Python console without claiming action success."""
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
            self._record_blender_result(
                "FAILED",
                description,
                reason=f"Could not focus or launch Blender for {description}.",
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
            if len(wrapped) > 1800:
                safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", description)[:60] or "blender_script"
                script_path = os.path.join(tempfile.gettempdir(), f"ayeye_{safe_name}.py")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(wrapped)
                console_command = (
                    "exec(compile(open("
                    f"{script_path!r}, 'r', encoding='utf-8'"
                    f").read(), {script_path!r}, 'exec'))"
                )
            else:
                console_command = f"exec({wrapped!r})"

            pyperclip.copy(console_command)
            time.sleep(0.1)
            # A harmless click in the main viewport makes sure Blender, not the
            # Ay-Eye overlay or terminal, owns keyboard focus before Shift+F4.
            try:
                pyautogui.click(self.screen_w // 2, self.screen_h // 2)
                time.sleep(0.15)
                pyautogui.press("escape")
                time.sleep(0.1)
            except Exception:
                pass
            pyautogui.hotkey("shift", "f4")
            time.sleep(0.9)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            pyautogui.press("enter")
            time.sleep(0.2)
            pyautogui.press("enter")
            time.sleep(0.8)
            if restore_layout:
                pyautogui.hotkey("shift", "f5")

            try:
                from core.state.short_term import short_term_memory
                short_term_memory.add_system_context(
                    f"BLENDER_BRIDGE_BOOTSTRAP [SENT]: {description}. Waiting for localhost bridge."
                )
            except Exception:
                pass
            logger.logger.info(f"Executor: Sent Blender bootstrap script: {description}")
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
            
        # Only record success for meaningful multi-step sequences (not single clicks)
        if not self._stop_event.is_set() and len(actions) >= 2:
            try:
                from core.state.manager import state_manager
                st = state_manager.get_state()
                summary = f"Finished {len(actions)} actions: {', '.join(a.get('type', '?') for a in actions[:3])}"
                rag_manager.remember_success("action_sequence", (st.app or "desktop"), (st.window or "desktop"), summary)
            except Exception:
                pass  # RAG write failure must never block executor

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
                original_point = (x, y) if x is not None and y is not None else None

                locator_result = None
                if target_name and screen_locator.is_specific_target(target_name):
                    locator_result = screen_locator.locate(
                        target_name,
                        frame=frame_before,
                        methods=("uia", "ocr"),
                        min_confidence=0.62,
                    )
                    if not locator_result and original_point:
                        locator_result = screen_locator.locate(
                            target_name,
                            frame=frame_before,
                            methods=("visual",),
                            min_confidence=0.45,
                            approximate=original_point,
                        )
                    if locator_result:
                        x, y = locator_result.x, locator_result.y
                        action["x"] = x
                        action["y"] = y
                
                if x is not None and y is not None:
                    self._click_with_retry(
                        x,
                        y,
                        button,
                        clicks,
                        frame_before,
                        target_name,
                        locator_result,
                        original_point,
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
                        reason = "Blender is active. OCR cannot read Blender's OpenGL fonts. Use blender_import_file, blender_open_import_menu, blender_create_scene, blender_python, or keyboard shortcuts instead."
                        short_term_memory.add_system_context(f"CLICK_TEXT BLOCKED: {reason}")
                        logger.logger.warning("Executor: click_text blocked - Blender active, OCR won't work")
                        
                        # Record as app rule in RAG (deduped by content hash)
                        try:
                            rag_manager.add_app_rule("blender", "Blender uses OpenGL UI and click_text should be avoided. Use Blender API actions or shortcuts.")
                        except Exception:
                            pass  # RAG write failure must never block executor
                        
                        bus.publish("ACTION_COMPLETED", action)
                        return
                    
                    locator_result = screen_locator.locate(
                        text_to_find,
                        frame=frame_before,
                        methods=("uia", "ocr"),
                        min_confidence=0.62,
                    )

                    if locator_result:
                        self._click_with_retry(
                            locator_result.x,
                            locator_result.y,
                            button,
                            clicks,
                            frame_before,
                            text_to_find,
                            locator_result,
                            original_point=(locator_result.x, locator_result.y),
                        )
                        from core.state.short_term import short_term_memory
                        short_term_memory.add_system_context(
                            f"CLICK_TEXT: Found '{text_to_find}' via {locator_result.method} "
                            f"at ({locator_result.x}, {locator_result.y}), clicked successfully."
                        )
                    else:
                        from core.state.short_term import short_term_memory
                        reason = f"Could not find '{text_to_find}' on screen using UI Automation or OCR."
                        short_term_memory.add_system_context(
                            f"CLICK_TEXT FAILED: {reason} "
                            f"This app may use custom-rendered UI that accessibility/OCR cannot read. "
                            f"FALLBACK OPTIONS: 1) Use coordinate-based click with the grid overlay. "
                            f"2) Use keyboard shortcuts or app-specific APIs. "
                            f"3) Try a shorter or slightly different text label."
                        )
                        logger.logger.warning(f"Executor: Locator could not find text '{text_to_find}'")
                        
                        # Record failure in RAG
                        try:
                            from core.state.manager import state_manager
                            st = state_manager.get_state()
                            rag_manager.remember_failure(f"click_text: {text_to_find}", (st.app or "unknown"), (st.window or "unknown"), reason)
                        except Exception:
                            pass  # RAG write failure must never block executor

                    bus.publish("ACTION_COMPLETED", action)
                    return

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
                                    
                                    # Record failure in RAG
                                    try:
                                        from core.state.manager import state_manager
                                        st = state_manager.get_state()
                                        rag_manager.remember_failure(command, (st.app or "powershell"), (st.window or "terminal"), errors[:500])
                                    except Exception:
                                        pass  # RAG write failure must never block executor
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
                if self._should_redirect_blender_python_to_scene(action):
                    source_text = action.get("source_user_text") or description
                    scene_description = (
                        f"{source_text}. Create a detailed Blender scene from the user's request. "
                        "If this is a container cafe, include a corrugated shipping-container body, "
                        "service window, counter, awning, signage, outdoor seating, planters, "
                        "warm lights, camera, and scene lighting. If this is an MLO request, "
                        "include room volume guides, portal guides, collision proxy guides, "
                        "template-specific interior props, labels, lighting, and camera."
                    )
                    reference_summary = " ".join(
                        part for part in (str(action.get("description") or ""), str(source_text or "")) if part
                    )[:500]
                    logger.log_event("BLENDER_PYTHON_REDIRECTED_TO_SCENE", {
                        "description": description[:160],
                        "source_user_text": str(source_text)[:160],
                    })
                    try:
                        from core.state.short_term import short_term_memory
                        short_term_memory.add_system_context(
                            "BLENDER_ACTION_REDIRECTED: blender_python -> blender_create_scene because this is a creative scene request."
                        )
                    except Exception:
                        pass
                    success = self._run_blender_create_scene(scene_description, reference_summary)
                else:
                    success = self._send_python_to_blender_console(script, description, restore_layout)
                if not success:
                    bus.publish("ACTION_ABORTED", {"reason": f"Blender API action failed: {description}"})
                    return

            elif a_type == "blender_create_scene":
                description = action.get("description") or action.get("prompt") or ""
                reference_summary = action.get("reference_summary") or ""
                label = description[:90] or "reference scene"
                success = self._run_blender_create_scene(description, reference_summary)
                if not success:
                    bus.publish("ACTION_ABORTED", {"reason": f"Blender scene creation failed: {label}"})
                    return

            elif a_type == "blender_bridge_status":
                success = self._check_blender_bridge_status()
                if not success:
                    bus.publish("ACTION_ABORTED", {"reason": "Could not check Blender bridge status"})
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
            if a_type in ["type", "hotkey"]:
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
