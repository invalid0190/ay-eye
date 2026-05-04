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
        """Returns a formatted string of learned skills relevant to the current prompt."""
        if not os.path.exists(self.skills_dir):
            return ""
            
        skills_text = []
        try:
            for filename in os.listdir(self.skills_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.skills_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f:
                        skill = json.load(f)
                        name = skill.get("name", filename)
                        instruction = skill.get("instruction", "")
                        if not self._should_include_skill(name, query_text, active_app, active_window):
                            continue
                        skills_text.append(f"Skill [{name}]: {instruction}")
        except Exception as e:
            logger.logger.error(f"Failed to load skills: {e}")
            
        if not skills_text:
            return ""
            
        return "\n--- LEARNED SKILLS ---\n" + "\n".join(skills_text) + "\n----------------------\n"

    def learn_skill(self, name: str, instruction: str) -> bool:
        """Save a new skill to the disk."""
        try:
            safe_name = "".join(c for c in name if c.isalnum() or c == "_").lower()
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

skill_manager = SkillManager()
