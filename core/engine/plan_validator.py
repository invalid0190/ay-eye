"""
Plan Validator — ensures multi-step LLM responses include a coherent plan.

For complex tasks (multi-action, high-risk), the LLM should first produce
a ``plan`` field listing the steps it intends to take.  This validator
checks:

  1. Plan exists when required (multi-action or high-risk responses).
  2. Actions roughly correspond to plan steps (no hidden actions).
  3. High-risk actions (cmd, write_file, blender_python) are explained.
  4. No obvious plan/action contradictions.

Verdict shape:
  {
      "valid": bool,
      "reason": str,      # Human-readable explanation
      "warnings": list,   # Non-blocking observations
  }

Design constraints:
  • Purely structural — does NOT call the LLM or do semantic similarity.
  • Sub-millisecond — string matching only.
  • Never raises.
"""

from __future__ import annotations

from core.config import sys_config
from core.utils.logger import logger

# Action types considered high-risk (must appear in plan rationale)
_HIGH_RISK_TYPES = {"cmd", "write_file", "blender_python", "blender_create_scene"}

# Action types that can appear without a plan (trivial / informational)
_TRIVIAL_TYPES = {
    "scroll", "read_file", "list_dir", "ocr_screen",
    "listen_audio", "extract_clipboard",
}


def _verdict(valid: bool, reason: str = "", warnings: list | None = None) -> dict:
    return {"valid": valid, "reason": reason, "warnings": warnings or []}


class PlanValidator:
    """Validates that LLM responses include a plan when needed."""

    def validate(self, response: dict) -> dict:
        """Validate *response* and return a verdict dict.

        Parameters
        ----------
        response : dict
            The full LLM response containing ``actions``, ``plan`` (optional),
            ``intent``, ``status``, ``confidence``, etc.
        """
        if not sys_config.get("planner_mode_enabled"):
            return _verdict(True, "Planner mode disabled")

        actions = response.get("actions") or []
        plan = response.get("plan") or []
        intent = response.get("intent", "")

        # Only validate "act" intents
        if intent != "act":
            return _verdict(True, "Non-action intent, no plan needed")

        # Filter out trivial actions for plan requirements
        significant_actions = [a for a in actions if a.get("type") not in _TRIVIAL_TYPES]
        high_risk_actions = [a for a in actions if a.get("type") in _HIGH_RISK_TYPES]

        warnings: list[str] = []

        # ── Check 1: Plan required for multi-action sequences ────────
        if (
            sys_config.get("require_plan_for_multi_action")
            and len(significant_actions) >= 3
            and not plan
        ):
            reason = (
                f"Response contains {len(significant_actions)} significant actions "
                f"but no plan. Multi-action responses require a 'plan' field."
            )
            logger.log_event("PLAN_VALIDATION_FAILED", {"reason": reason})
            return _verdict(False, reason)

        # ── Check 2: Plan required for high-risk actions ─────────────
        if (
            sys_config.get("require_plan_for_high_risk")
            and high_risk_actions
            and not plan
        ):
            types_str = ", ".join(a.get("type", "?") for a in high_risk_actions)
            reason = (
                f"High-risk actions [{types_str}] present but no plan provided. "
                f"Add a 'plan' field explaining why each high-risk action is needed."
            )
            logger.log_event("PLAN_VALIDATION_FAILED", {"reason": reason})
            return _verdict(False, reason)

        # If no plan was given and none was required, pass
        if not plan:
            return _verdict(True, "No plan required for this response")

        # ── Check 3: Plan is well-formed ─────────────────────────────
        if not isinstance(plan, list) or not all(isinstance(s, str) for s in plan):
            reason = "Plan must be a list of strings."
            logger.log_event("PLAN_VALIDATION_FAILED", {"reason": reason})
            return _verdict(False, reason)

        if len(plan) == 0:
            reason = "Plan is empty."
            logger.log_event("PLAN_VALIDATION_FAILED", {"reason": reason})
            return _verdict(False, reason)

        # ── Check 4: Actions ≤ 2× plan steps (no hidden bulk) ───────
        if len(significant_actions) > len(plan) * 2 + 2:
            reason = (
                f"Too many actions ({len(significant_actions)}) for the plan "
                f"({len(plan)} steps). Actions may include hidden operations "
                f"not described in the plan."
            )
            logger.log_event("PLAN_VALIDATION_FAILED", {"reason": reason})
            return _verdict(False, reason, warnings)

        # ── Check 5: High-risk actions mentioned in plan ─────────────
        plan_text_lower = " ".join(plan).lower()
        for action in high_risk_actions:
            a_type = action.get("type", "")
            # Check if the plan mentions the action type or a related keyword
            related_keywords = _RISK_KEYWORDS.get(a_type, [a_type])
            if not any(kw in plan_text_lower for kw in related_keywords):
                warnings.append(
                    f"High-risk action '{a_type}' not clearly referenced in plan."
                )

        # ── Check 6: No contradictory plan+action pairs ──────────────
        action_types_present = {a.get("type") for a in actions}

        # If plan mentions "do NOT click" but actions contain click
        for step in plan:
            step_lower = step.lower()
            if ("do not click" in step_lower or "don't click" in step_lower) and (
                "click" in action_types_present or "click_text" in action_types_present
            ):
                reason = (
                    f"Plan says '{step[:80]}' but actions include click/click_text. "
                    f"This is contradictory."
                )
                logger.log_event("PLAN_VALIDATION_FAILED", {"reason": reason})
                return _verdict(False, reason, warnings)

            if ("do not type" in step_lower or "don't type" in step_lower) and (
                "type" in action_types_present
            ):
                reason = (
                    f"Plan says '{step[:80]}' but actions include type. "
                    f"This is contradictory."
                )
                logger.log_event("PLAN_VALIDATION_FAILED", {"reason": reason})
                return _verdict(False, reason, warnings)

        # ── Passed all checks ────────────────────────────────────────
        if warnings:
            logger.log_event("PLAN_VALIDATED_WITH_WARNINGS", {
                "warnings": warnings[:3],
                "plan_steps": len(plan),
                "actions": len(actions),
            })
        else:
            logger.log_event("PLAN_VALIDATED", {
                "plan_steps": len(plan),
                "actions": len(actions),
            })
        return _verdict(True, "Plan validated", warnings)


# Keywords the plan might use to reference high-risk action types
_RISK_KEYWORDS: dict[str, list[str]] = {
    "cmd": ["cmd", "command", "terminal", "powershell", "shell", "run", "execute", "mkdir", "install"],
    "write_file": ["write", "file", "create file", "save", "output"],
    "blender_python": ["blender", "python", "script", "bpy"],
    "blender_create_scene": ["blender", "scene", "model", "create", "reference"],
}

plan_validator = PlanValidator()
