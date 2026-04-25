import json
import re
from typing import Dict, Any, Optional
from core.utils.logger import logger

class JSONHealingParser:
    @staticmethod
    def extract_and_heal(text: str) -> Optional[Dict[str, Any]]:
        try:
            if not text:
                return None
                
            # 1. Strip markdown code fences
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)
            text = text.strip()
            
            # 2. Extract first JSON block
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                logger.logger.warning("No JSON block found in response")
                return None
            
            json_str = match.group(0)
            
            # 3. Basic Healing
            json_str = re.sub(r',\s*\}', '}', json_str)
            json_str = re.sub(r',\s*\]', ']', json_str)
            
            # 4. Parse
            data = json.loads(json_str)
            
            # 5. Fill defaults for missing fields
            data.setdefault("intent", "guide")
            data.setdefault("message", "")
            data.setdefault("actions", [])
            data.setdefault("confidence", 0.8)
            
            return data
        except Exception as e:
            logger.logger.error(f"JSON healing failed: {e}")
            return None

json_parser = JSONHealingParser()
