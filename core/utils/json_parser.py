import json
import re
from typing import Dict, Any, Optional
from core.utils.logger import logger

class JSONHealingParser:
    @staticmethod
    def extract_and_heal(text: str) -> Optional[Dict[str, Any]]:
        try:
            # 1. Extract first JSON block
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                logger.logger.warning("No JSON block found in response")
                return None
            
            json_str = match.group(0)
            
            # 2. Basic Healing
            # Fix missing quotes on keys (simple version)
            json_str = re.sub(r'(\w+):', r'"\1":', json_str)
            # Fix trailing commas
            json_str = re.sub(r',\s*\}', '}', json_str)
            json_str = re.sub(r',\s*\]', ']', json_str)
            
            # 3. Parse
            data = json.loads(json_str)
            
            # 4. Validate Schema
            required = ["intent", "message", "actions", "confidence"]
            if all(k in data for k in required):
                return data
            
            logger.logger.warning(f"Schema validation failed: {data.keys()}")
            return None
        except Exception as e:
            logger.logger.error(f"JSON healing failed: {e}")
            return None

json_parser = JSONHealingParser()
