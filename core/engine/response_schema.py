"""
LLM Response Schema Validator — sanitizes and normalizes LLM output
before any downstream pipeline (Plan Validator, Safety, Executor, Verifier).

Ensures:
  * Required fields exist with correct types.
  * Actions are well-formed dicts with valid types and required sub-fields.
  * Expect contracts inside actions are structurally valid.
  * Dangerous/unknown top-level fields are stripped.
  * Sensible defaults applied for missing optional fields.

Returns a verdict:
  {
      "valid": bool,          # True if response is usable (may be normalized)
      "reason": str,          # '' if valid, explanation if invalid
      "response": dict,       # The cleaned/normalized response
      "removed_actions": int, # Count of actions stripped during validation
  }

Design constraints:
  * Pure dict manipulation, sub-millisecond.
  * Never raises.
  * Idempotent — safe to call multiple times.
"""

from __future__ import annotations

from core.utils.logger import logger

# ── Constants ────────────────────────────────────────────────────────

_VALID_INTENTS = {"act", "guide", "ask", "ignore"}
_VALID_STATUSES = {"in_progress", "complete", "failed"}

_VALID_ACTION_TYPES = {
    "click", "click_text", "drag", "type", "hotkey", "scroll", "switch", "launch",
    "open_url", "cmd", "create_skill", "read_file", "list_dir",
    "write_file", "extract_clipboard", "listen_audio", "ocr_screen",
    "blender_python", "blender_open_import_menu", "blender_import_file",
}

# Per-action-type required fields (at least ONE of these must be present)
_ACTION_REQUIRED_FIELDS: dict[str, list[str]] = {
    "click": ["x", "y"],              # or "target" — handled specially
    "click_text": ["text"],
    "drag": ["x1", "y1", "x2", "y2"],
    "type": ["text"],
    "hotkey": ["keys"],
    "cmd": ["command"],
    "write_file": ["path", "content"],
    "open_url": ["url"],
    "switch": ["target"],
    "launch": ["target"],
    "blender_python": ["script"],
    "blender_import_file": ["path"],
    "create_skill": ["name", "instruction"],
    "read_file": ["path"],
    "list_dir": ["path"],
}

_VALID_EXPECT_TYPES = {
    "screen_text", "file_exists", "window_title",
    "cmd_success", "app_focused", "clipboard_contains", "none",
}

_EXPECT_VALUE_REQUIRED = {
    "file_exists", "app_focused", "window_title",
    "screen_text", "clipboard_contains",
}

# Fields allowed at the top level of a response
_ALLOWED_TOP_LEVEL = {
    "intent", "status", "message", "actions", "confidence",
    "plan", "mode", "speech",
}

_MAX_MESSAGE_LENGTH = 4000
_MAX_EXPECT_TIMEOUT = 5


# ── Public API ───────────────────────────────────────────────────────

class ResponseSchemaValidator:
    """Validate and normalize a raw LLM response dict."""

    def validate(self, response: dict | None) -> dict:
        """Return ``{valid, reason, response, removed_actions}``."""
        if response is None or not isinstance(response, dict):
            return self._invalid("Response is not a dict (got None or non-dict)")

        # Work on a copy so we don't mutate the original
        resp = dict(response)
        removed = 0

        # ── 1. Strip unknown top-level keys ──────────────────────
        unknown_keys = set(resp.keys()) - _ALLOWED_TOP_LEVEL
        for k in unknown_keys:
            resp.pop(k, None)

        # ── 2. Normalize intent ──────────────────────────────────
        intent = resp.get("intent")
        if intent not in _VALID_INTENTS:
            if intent is None:
                resp["intent"] = "ignore"
            else:
                logger.logger.warning(f"Schema: Unknown intent '{intent}', defaulting to 'ignore'")
                resp["intent"] = "ignore"

        # ── 3. Normalize status ──────────────────────────────────
        status = resp.get("status")
        if status not in _VALID_STATUSES:
            resp["status"] = "failed" if resp["intent"] == "act" else "complete"

        # ── 4. Normalize message ─────────────────────────────────
        message = resp.get("message")
        if not isinstance(message, str):
            resp["message"] = ""
        else:
            # Collapse multiline to single line
            resp["message"] = " ".join(message.split())
            # Cap length
            if len(resp["message"]) > _MAX_MESSAGE_LENGTH:
                resp["message"] = resp["message"][:_MAX_MESSAGE_LENGTH]

        # ── 5. Normalize confidence ──────────────────────────────
        conf = resp.get("confidence")
        if not isinstance(conf, (int, float)):
            resp["confidence"] = 0.0
        else:
            resp["confidence"] = max(0.0, min(1.0, float(conf)))

        # ── 6. Normalize actions ─────────────────────────────────
        actions = resp.get("actions")
        if not isinstance(actions, list):
            resp["actions"] = []
        else:
            clean_actions = []
            for i, action in enumerate(actions):
                result = self._validate_action(action, i)
                if result is not None:
                    clean_actions.append(result)
                else:
                    removed += 1
            resp["actions"] = clean_actions

        # ── 7. Normalize plan (optional) ─────────────────────────
        plan = resp.get("plan")
        if plan is not None:
            if isinstance(plan, list):
                resp["plan"] = [str(s) for s in plan if isinstance(s, str)]
            else:
                # Non-list plan is dropped
                resp.pop("plan", None)

        # ── 8. Final validity check ──────────────────────────────
        # An "act" intent with zero remaining actions after cleanup
        if resp["intent"] == "act" and len(resp["actions"]) == 0 and removed > 0:
            reason = f"All {removed} actions were invalid and removed"
            logger.log_event("RESPONSE_SCHEMA_INVALID", {"reason": reason})
            return self._invalid(reason, resp, removed)

        if removed > 0:
            logger.log_event("RESPONSE_SCHEMA_NORMALIZED", {
                "removed_actions": removed,
                "remaining_actions": len(resp["actions"]),
            })

        return {
            "valid": True,
            "reason": "",
            "response": resp,
            "removed_actions": removed,
        }

    # ── Action validation ────────────────────────────────────────

    def _validate_action(self, action, index: int) -> dict | None:
        """Return cleaned action or None to remove it."""
        if not isinstance(action, dict):
            logger.logger.warning(f"Schema: Action [{index}] is not a dict, removing")
            return None

        a_type = action.get("type")
        if not isinstance(a_type, str) or a_type not in _VALID_ACTION_TYPES:
            logger.logger.warning(f"Schema: Action [{index}] has invalid type '{a_type}', removing")
            return None

        # Check required fields
        required = _ACTION_REQUIRED_FIELDS.get(a_type)
        if required:
            # Special case: click can have x/y OR target
            if a_type == "click":
                has_coords = "x" in action and "y" in action
                has_target = "target" in action
                if not has_coords and not has_target:
                    logger.logger.warning(
                        f"Schema: Action [{index}] click missing x/y and target, removing"
                    )
                    return None
            else:
                missing = [f for f in required if f not in action]
                if missing:
                    logger.logger.warning(
                        f"Schema: Action [{index}] {a_type} missing fields {missing}, removing"
                    )
                    return None

        # Validate expect contract if present
        expect = action.get("expect")
        if expect is not None:
            cleaned_expect = self._validate_expect(expect, index)
            if cleaned_expect is not None:
                action = dict(action)  # Don't mutate original
                action["expect"] = cleaned_expect
            else:
                action = dict(action)
                action.pop("expect", None)

        return action

    # ── Expect validation ────────────────────────────────────────

    def _validate_expect(self, expect, action_index: int) -> dict | None:
        """Return cleaned expect or None to remove it."""
        if not isinstance(expect, dict):
            logger.logger.warning(
                f"Schema: Action [{action_index}] expect is not a dict, removing"
            )
            return None

        expect_type = expect.get("type")
        if not isinstance(expect_type, str) or expect_type not in _VALID_EXPECT_TYPES:
            logger.logger.warning(
                f"Schema: Action [{action_index}] expect has invalid type '{expect_type}', removing"
            )
            return None

        # Check value required
        if expect_type in _EXPECT_VALUE_REQUIRED:
            value = expect.get("value")
            if not isinstance(value, str) or not value:
                logger.logger.warning(
                    f"Schema: Action [{action_index}] expect.{expect_type} missing 'value', removing"
                )
                return None

        # Cap timeout
        result = dict(expect)
        timeout = result.get("timeout")
        if timeout is not None:
            if not isinstance(timeout, (int, float)):
                result.pop("timeout", None)
            else:
                result["timeout"] = min(max(0, float(timeout)), _MAX_EXPECT_TIMEOUT)

        return result

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _invalid(reason: str, response: dict | None = None, removed: int = 0) -> dict:
        return {
            "valid": False,
            "reason": reason,
            "response": response or {},
            "removed_actions": removed,
        }


response_schema = ResponseSchemaValidator()
