import os
import json
from core.utils.logger import logger

class SkillManager:
    def __init__(self):
        self.skills_dir = os.path.join(os.getcwd(), "core", "skills")
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir, exist_ok=True)

    _SOLLUMZ_TRIGGER_TERMS = (
        "sollumz", "fivem", "gta", "mlo", "codewalker", "ydr", "ydd", "ybn",
        "ytyp", "ymap", "drawable", "archetype", "collision mesh", "portal",
    )

    def _should_include_skill(self, name: str, query_text: str = "", active_app: str = "", active_window: str = "") -> bool:
        """Keep narrow workflow skills out of unrelated prompts."""
        skill_name = (name or "").lower()
        context = f"{query_text or ''} {active_app or ''} {active_window or ''}".lower()

        if skill_name == "blender_sollumz":
            return any(term in context for term in self._SOLLUMZ_TRIGGER_TERMS)

        return True

    def get_all_skills_context(self, query_text: str = "", active_app: str = "", active_window: str = "") -> str:
        """Returns a formatted string of learned skills relevant to the current prompt.

        For mimic-recorded skills (those with a ``recorded_actions`` array)
        we also surface the pre-built action list so the brain can replay
        them verbatim instead of re-deriving steps from a free-text
        instruction. The section is delimited so the prompt stays
        unambiguous even if a user-written instruction happens to contain
        JSON-looking text.
        """
        if not os.path.exists(self.skills_dir):
            return ""

        skills_text = []
        try:
            for filename in os.listdir(self.skills_dir):
                if not filename.endswith(".json"):
                    continue
                filepath = os.path.join(self.skills_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    skill = json.load(f)
                name = skill.get("name", filename)
                instruction = skill.get("instruction", "")
                if not self._should_include_skill(name, query_text, active_app, active_window):
                    continue

                recorded = skill.get("recorded_actions")
                if isinstance(recorded, list) and recorded:
                    description = skill.get("description") or instruction
                    actions_json = json.dumps(recorded, ensure_ascii=False)
                    skills_text.append(
                        f"Skill [{name}] (recorded, {len(recorded)} actions): {description}\n"
                        f"  RECORDED_ACTIONS: {actions_json}"
                    )
                else:
                    skills_text.append(f"Skill [{name}]: {instruction}")
        except Exception as e:
            logger.logger.error(f"Failed to load skills: {e}")

        if not skills_text:
            return ""

        return "\n--- LEARNED SKILLS ---\n" + "\n".join(skills_text) + "\n----------------------\n"

    def learn_skill(self, name: str, instruction: str) -> bool:
        """Save a free-text skill (LLM-described workflow) to disk."""
        try:
            safe_name = self._safe_filename(name)
            if not safe_name:
                return False

            filepath = os.path.join(self.skills_dir, f"{safe_name}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "name": name,
                    "instruction": instruction
                }, f, indent=4)

            logger.logger.info(f"Learned new skill: {name}")
            return True
        except Exception as e:
            logger.logger.error(f"Failed to save skill {name}: {e}")
            return False

    # ── Mimic Mode integration ───────────────────────────────────────

    def save_recorded_skill(self, skill: dict) -> bool:
        """Persist a Mimic-Mode skill produced by ``skill_synthesizer``.

        Expected dict shape::

            {
              "name": "morning routine",
              "description": "Open Discord, then VS Code, then start dev server",
              "instruction": "...",
              "recorded_actions": [{...}, ...],
              "raw_event_count": 42,
            }
        """
        try:
            name = skill.get("name") or ""
            safe_name = self._safe_filename(name)
            if not safe_name:
                logger.logger.warning(
                    f"SkillManager: cannot save recorded skill, "
                    f"name '{name}' has no safe characters"
                )
                return False

            actions = skill.get("recorded_actions")
            if not isinstance(actions, list) or not actions:
                logger.logger.warning(
                    f"SkillManager: refusing to save recorded skill '{name}' — "
                    "no recorded_actions"
                )
                return False

            payload = {
                "name": name,
                "description": skill.get("description", ""),
                "instruction": skill.get("instruction", ""),
                "recorded_actions": actions,
                "raw_event_count": int(skill.get("raw_event_count", 0)),
                "kind": "recorded",
            }
            filepath = os.path.join(self.skills_dir, f"{safe_name}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
            logger.logger.info(
                f"SkillManager: saved recorded skill '{name}' "
                f"({len(actions)} actions) -> {filepath}"
            )
            return True
        except Exception as e:
            logger.logger.error(f"SkillManager: failed to save recorded skill: {e}")
            return False

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Normalise a user-supplied skill name for use as a filename."""
        if not name:
            return ""
        cleaned = []
        for c in name:
            if c.isalnum():
                cleaned.append(c)
            elif c in (" ", "-", "_"):
                cleaned.append("_")
        result = "".join(cleaned).strip("_").lower()
        # Avoid collapsing spaces of the form "morning  routine" into ____
        while "__" in result:
            result = result.replace("__", "_")
        return result

skill_manager = SkillManager()
