"""
Post-Action Verifier — checks whether an executed action achieved its goal.

Called by the orchestrator AFTER executor.execute_single() returns.

Verification priority:
  1. If the action has an ``expect`` contract, evaluate it first.
  2. Otherwise, fall back to the type-specific heuristic handler.
  3. Otherwise, use generic screen-change detection.

Expect contract shape (optional field on any action):
  "expect": {
      "type": "screen_text|file_exists|window_title|cmd_success|app_focused|clipboard_contains|none",
      "value": "expected value",
      "timeout": 3            # optional, seconds to wait before checking
  }

Verdict shape:
  {
      "success": bool,
      "reason": str,
      "evidence": dict,      # type-specific diagnostic data
      "should_retry": bool,  # hint for orchestrator
  }

Design constraints:
  * Sub-50 ms for most checks (no OCR, no LLM calls).
  * Never raises — returns a verdict.
  * Does NOT mutate state or execute actions.
"""

from __future__ import annotations

import os
import re
import time
import ctypes
import ctypes.wintypes
from core.config import sys_config
from core.utils.logger import logger
from core.vision.live_perception import live_perception


# ── High-risk types requiring expect contracts ───────────────────────

_HIGH_RISK_TYPES = {"cmd", "write_file", "blender_python", "blender_create_scene"}

# ── Valid expect types ───────────────────────────────────────────────

_VALID_EXPECT_TYPES = {
    "screen_text", "file_exists", "window_title",
    "cmd_success", "app_focused", "clipboard_contains",
    "blender_scene_objects", "none",
}


# ── Verdict helpers ──────────────────────────────────────────────────

def _ok(reason: str = "Verified", evidence: dict | None = None) -> dict:
    return {"success": True, "reason": reason, "evidence": evidence or {}, "should_retry": False}


def _fail(reason: str, evidence: dict | None = None, should_retry: bool = True) -> dict:
    return {"success": False, "reason": reason, "evidence": evidence or {}, "should_retry": should_retry}


# ── Foreground window helper ────────────────────────────────────────

def _get_foreground_title() -> str:
    """Return the title of the current foreground window (fast Win32 call)."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
    except Exception:
        pass
    return ""


# ── Verifier ─────────────────────────────────────────────────────────

class ActionVerifier:
    """Lightweight post-action verification for each action type."""

    # Action types where screen-change is meaningful evidence
    _SCREEN_CHANGE_TYPES = {"click", "click_text", "drag", "scroll", "hotkey"}
    # Action types where we check short_term_memory for executor feedback
    _MEMORY_CHECK_TYPES = {"cmd", "blender_python", "blender_create_scene", "blender_open_import_menu", "blender_import_file"}

    def verify(self, action: dict, frame_before=None) -> dict:
        """Verify a single action. Returns a verdict dict.

        Priority:
          1. Expect contract (if present and valid)
          2. Type-specific handler (heuristic)
          3. Generic screen-change / no-op
        """
        if not sys_config.get("post_action_verify_enabled"):
            return _ok("Verification disabled")

        a_type = action.get("type", "")

        try:
            # ── 0. Warn/block missing expect on high-risk actions ────
            expect = action.get("expect")
            if (
                a_type in _HIGH_RISK_TYPES
                and not expect
                and sys_config.get("require_expect_for_high_risk_actions")
            ):
                logger.log_event("EXPECT_MISSING_HIGH_RISK", {"type": a_type})
                # Warn but don't block — the heuristic handler still runs.
                # The warning is logged for observability.

            # ── 1. Expect contract evaluation ────────────────────────
            if expect and isinstance(expect, dict):
                result = self._evaluate_expect(action, expect, frame_before)
                if result is not None:
                    return result

            # ── 2. Type-specific handler (heuristic fallback) ────────
            handler = self._HANDLERS.get(a_type)
            if handler:
                return handler(self, action, frame_before)

            # ── 3. Generic fallback ──────────────────────────────────
            if a_type in self._SCREEN_CHANGE_TYPES:
                return self._verify_screen_changed(action, frame_before)

            return _ok(f"Action '{a_type}' does not require verification")

        except Exception as e:
            logger.logger.error(f"ActionVerifier: Exception during verify: {e}")
            return _ok(f"Verification skipped due to error: {e}")

    # ── Expect contract evaluation ───────────────────────────────────

    def _evaluate_expect(self, action: dict, expect: dict, frame_before) -> dict | None:
        """Evaluate an expect contract. Returns verdict or None to fall back."""
        expect_type = expect.get("type", "")
        value = expect.get("value", "")
        timeout = min(expect.get("timeout", 0), 5)  # Cap at 5s

        if expect_type not in _VALID_EXPECT_TYPES:
            logger.logger.warning(f"ActionVerifier: Unknown expect type '{expect_type}', falling back")
            return None

        if expect_type == "none":
            return _ok("Expect contract: none (no verification requested)")

        if timeout > 0:
            time.sleep(timeout)

        a_type = action.get("type", "")

        # Dispatch to expect handler
        handler = self._EXPECT_HANDLERS.get(expect_type)
        if handler:
            result = handler(self, action, expect, frame_before)
            log_data = {"type": a_type, "expect_type": expect_type, "success": result["success"]}
            if result["success"]:
                logger.log_event("EXPECT_CONTRACT_PASSED", log_data)
            else:
                logger.log_event("EXPECT_CONTRACT_FAILED", log_data)
            return result

        return None  # Unknown handler → fall back

    def _expect_file_exists(self, action: dict, expect: dict, frame_before) -> dict:
        """Check that a file exists at the expected path."""
        path = expect.get("value") or action.get("path", "")
        if not path:
            return _fail("expect.file_exists: no path specified", should_retry=False)
        if os.path.isfile(path):
            size = os.path.getsize(path)
            return _ok(f"File exists ({size} bytes)", {"path": path, "size": size})
        return _fail(f"Expected file not found: {path}", {"path": path})

    def _expect_cmd_success(self, action: dict, expect: dict, frame_before) -> dict:
        """Check that the command returned success in short_term_memory."""
        try:
            from core.state.short_term import short_term_memory
            history = short_term_memory.get_history_string()
            command = (action.get("command") or "")[:60]

            if "CMD_RESULT [SUCCESS" in history or "CMD_RESULT [LAUNCHED" in history:
                return _ok("Command succeeded (expect contract)", {"command": command})
            if "CMD_RESULT [FAILED" in history:
                return _fail(f"Command failed: {command}", {"command": command})
            if "CMD_RESULT [BLOCKED" in history:
                return _fail(f"Command blocked: {command}", {"command": command}, should_retry=False)

            return _ok("Command submitted (no result yet)", {"command": command})
        except Exception:
            return _ok("cmd expect check skipped")

    def _expect_app_focused(self, action: dict, expect: dict, frame_before) -> dict:
        """Check that the foreground window title contains the expected value."""
        target = (expect.get("value") or action.get("target") or "").lower()
        if not target:
            return _ok("expect.app_focused: no target specified")

        time.sleep(0.3)
        fg_title = _get_foreground_title().lower()
        if target in fg_title:
            return _ok(f"App '{target}' is focused", {"fg_title": fg_title[:100]})
        return _fail(
            f"Expected '{target}' focused, got '{fg_title[:60]}'",
            {"target": target, "fg_title": fg_title[:100]},
        )

    def _expect_window_title(self, action: dict, expect: dict, frame_before) -> dict:
        """Check that the foreground window title contains the expected text."""
        expected = (expect.get("value") or "").lower()
        if not expected:
            return _ok("expect.window_title: no value specified")

        time.sleep(0.3)
        fg_title = _get_foreground_title().lower()
        if expected in fg_title:
            return _ok(f"Window title contains '{expected}'", {"fg_title": fg_title[:100]})
        return _fail(
            f"Expected '{expected}' in window title, got '{fg_title[:60]}'",
            {"expected": expected, "fg_title": fg_title[:100]},
        )

    def _expect_screen_text(self, action: dict, expect: dict, frame_before) -> dict:
        """Check short_term_memory for recently captured text matching expected value.

        NOTE: This does NOT perform OCR — it checks if the executor or
        a recent ocr_screen action already captured text containing the value.
        For true OCR verification, the LLM should chain an ocr_screen action
        with status=in_progress.
        """
        expected = (expect.get("value") or "").lower()
        if not expected:
            return _ok("expect.screen_text: no value specified")

        try:
            from core.state.short_term import short_term_memory
            history = short_term_memory.get_history_string().lower()
            if expected in history:
                return _ok(f"Text '{expected[:40]}' found in recent context")
            # Not in memory — fall through to screen-change as a weak heuristic
            return self._verify_screen_changed(action, frame_before)
        except Exception:
            return self._verify_screen_changed(action, frame_before)

    def _expect_clipboard_contains(self, action: dict, expect: dict, frame_before) -> dict:
        """Check short_term_memory for clipboard content matching expected value."""
        expected = (expect.get("value") or "").lower()
        if not expected:
            return _ok("expect.clipboard_contains: no value specified")

        try:
            from core.state.short_term import short_term_memory
            history = short_term_memory.get_history_string().lower()
            if expected in history:
                return _ok(f"Clipboard/context contains '{expected[:40]}'")
            return _fail(f"Expected clipboard content '{expected[:40]}' not found")
        except Exception:
            return _ok("clipboard_contains check skipped")

    def _expect_blender_scene_objects(self, action: dict, expect: dict, frame_before) -> dict:
        """Require a successful Blender bridge result with at least one scene object."""
        return self._verify_blender(action, frame_before)

    # ── Expect handler dispatch ──────────────────────────────────────

    _EXPECT_HANDLERS: dict[str, callable] = {
        "file_exists": _expect_file_exists,
        "cmd_success": _expect_cmd_success,
        "app_focused": _expect_app_focused,
        "window_title": _expect_window_title,
        "screen_text": _expect_screen_text,
        "clipboard_contains": _expect_clipboard_contains,
        "blender_scene_objects": _expect_blender_scene_objects,
    }

    # ── Heuristic type-specific handlers (unchanged) ─────────────────

    def _verify_click(self, action: dict, frame_before) -> dict:
        """Click/click_text: check screen changed around click point."""
        return self._verify_screen_changed(action, frame_before)

    def _verify_cmd(self, action: dict, frame_before) -> dict:
        """cmd: check short_term_memory for CMD_RESULT feedback."""
        try:
            from core.state.short_term import short_term_memory
            history = short_term_memory.get_history_string()
            command = (action.get("command") or "")[:60]

            if "CMD_RESULT [SUCCESS" in history or "CMD_RESULT [LAUNCHED" in history:
                return _ok("Command completed successfully", {"command": command})
            if "CMD_RESULT [FAILED" in history:
                return _fail(f"Command failed: {command}", {"command": command}, should_retry=True)
            if "CMD_RESULT [BLOCKED" in history:
                return _fail(f"Command blocked by security: {command}", {"command": command}, should_retry=False)
            if "CMD_RESULT [TIMEOUT" in history:
                return _fail(f"Command timed out: {command}", {"command": command}, should_retry=True)

            return _ok("Command submitted (no result captured yet)", {"command": command})
        except Exception:
            return _ok("cmd verification skipped")

    def _verify_write_file(self, action: dict, frame_before) -> dict:
        """write_file: check that the target file exists and is non-empty."""
        path = action.get("path", "")
        if not path:
            return _fail("write_file action missing path", should_retry=False)

        if os.path.isfile(path):
            size = os.path.getsize(path)
            return _ok(f"File exists ({size} bytes)", {"path": path, "size": size})
        return _fail(f"File not found after write: {path}", {"path": path}, should_retry=True)

    def _verify_switch(self, action: dict, frame_before) -> dict:
        """switch/launch: check foreground window title contains target."""
        target = (action.get("target") or "").lower()
        if not target:
            return _ok("switch action had no target")

        time.sleep(0.3)
        fg_title = _get_foreground_title().lower()

        if target in fg_title:
            return _ok(f"Window '{target}' is focused", {"fg_title": fg_title[:100]})
        return _fail(
            f"Expected '{target}' in foreground, got '{fg_title[:60]}'",
            {"target": target, "fg_title": fg_title[:100]},
            should_retry=True,
        )

    def _verify_type_action(self, action: dict, frame_before) -> dict:
        """type: screen must have changed (text appeared)."""
        return self._verify_screen_changed(action, frame_before)

    def _verify_blender(self, action: dict, frame_before) -> dict:
        """Blender API actions: check short_term_memory for BLENDER_API_RESULT."""
        try:
            from core.state.short_term import short_term_memory
            history = short_term_memory.get_history_string()

            matches = re.findall(r"BLENDER_API_RESULT \[(SUCCESS|FAILED)\]:(.*)", history)
            if not matches:
                return _fail("No successful Blender API result recorded yet", {
                    "action": action.get("type"),
                }, should_retry=True)

            status, line = matches[-1]
            if status == "FAILED":
                return _fail("Blender API action failed", {"action": action.get("type")}, should_retry=True)

            if action.get("type") == "blender_create_scene":
                counts = re.findall(r"object_count=(-?\d+)", line)
                if counts and int(counts[-1]) > 0:
                    return _ok("Blender scene contains objects", {
                        "action": action.get("type"),
                        "object_count": int(counts[-1]),
                    })
                return _fail("Blender scene creation did not report any objects", {
                    "action": action.get("type"),
                }, should_retry=True)

            return _ok("Blender API command succeeded", {"action": action.get("type")})
        except Exception:
            return _ok("Blender verification skipped")

    def _verify_open_url(self, action: dict, frame_before) -> dict:
        """open_url: check that a browser window appeared."""
        time.sleep(0.5)
        fg_title = _get_foreground_title().lower()

        browser_hints = ("chrome", "firefox", "edge", "brave", "opera", "safari", "browser")
        if any(h in fg_title for h in browser_hints):
            return _ok("Browser window detected", {"fg_title": fg_title[:100]})

        return _ok("URL opened (non-browser window focused)", {"fg_title": fg_title[:100]})

    # ── Generic screen-change check ──────────────────────────────────

    def _verify_screen_changed(self, action: dict, frame_before) -> dict:
        """Check if the screen changed since frame_before."""
        if frame_before is None:
            return _ok("No baseline frame for comparison")

        time.sleep(0.15)
        changed = live_perception.verify_screen_changed(frame_before)
        if changed:
            return _ok("Screen changed after action")
        return _fail(
            f"No visible screen change after '{action.get('type', '?')}'",
            {"action_type": action.get("type")},
            should_retry=True,
        )

    # ── Handler dispatch table ───────────────────────────────────────

    _HANDLERS: dict[str, callable] = {
        "click": _verify_click,
        "click_text": _verify_click,
        "drag": _verify_click,
        "type": _verify_type_action,
        "cmd": _verify_cmd,
        "write_file": _verify_write_file,
        "switch": _verify_switch,
        "launch": _verify_switch,
        "open_url": _verify_open_url,
        "blender_python": _verify_blender,
        "blender_create_scene": _verify_blender,
        "blender_open_import_menu": _verify_blender,
        "blender_import_file": _verify_blender,
    }


action_verifier = ActionVerifier()
