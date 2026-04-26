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
            
            # 3. Basic Healing — trailing commas
            json_str = re.sub(r',\s*\}', '}', json_str)
            json_str = re.sub(r',\s*\]', ']', json_str)
            
            # 4. Fix control characters inside strings (newlines, tabs, etc.)
            # Replace literal control characters with their escaped versions
            # But preserve valid JSON escapes like \n that are already in the source
            def fix_control_chars(s):
                """Replace raw control characters inside JSON string values."""
                result = []
                in_string = False
                escape = False
                for ch in s:
                    if escape:
                        result.append(ch)
                        escape = False
                        continue
                    if ch == '\\':
                        result.append(ch)
                        escape = True
                        continue
                    if ch == '"':
                        in_string = not in_string
                        result.append(ch)
                        continue
                    if in_string and ord(ch) < 32:
                        # Replace control characters with their escaped forms
                        if ch == '\n':
                            result.append('\\n')
                        elif ch == '\r':
                            result.append('\\r')
                        elif ch == '\t':
                            result.append('\\t')
                        else:
                            result.append(f'\\u{ord(ch):04x}')
                    else:
                        result.append(ch)
                return ''.join(result)
            
            json_str = fix_control_chars(json_str)
            
            # 5. Parse
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # Last resort: try to extract key fields manually
                data = JSONHealingParser._manual_extract(json_str)
                if not data:
                    logger.logger.error("JSON healing: all parse attempts failed")
                    return None
            
            # 6. Fill defaults for missing fields
            data.setdefault("intent", "guide")
            data.setdefault("message", "")
            data.setdefault("actions", [])
            data.setdefault("confidence", 0.8)
            
            return data
        except Exception as e:
            logger.logger.error(f"JSON healing failed: {e}")
            return None
    
    @staticmethod
    def _manual_extract(json_str: str) -> Optional[Dict[str, Any]]:
        """Last-resort extraction of key fields using regex."""
        try:
            result = {}
            
            # Extract intent
            m = re.search(r'"intent"\s*:\s*"(\w+)"', json_str)
            if m:
                result["intent"] = m.group(1)
            
            # Extract message (grab everything between quotes after "message":)
            m = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', json_str, re.DOTALL)
            if m:
                result["message"] = m.group(1).replace('\\n', '\n').replace('\\"', '"')
            
            # Extract confidence
            m = re.search(r'"confidence"\s*:\s*([\d.]+)', json_str)
            if m:
                result["confidence"] = float(m.group(1))
            
            # Extract actions array
            m = re.search(r'"actions"\s*:\s*(\[.*?\])', json_str, re.DOTALL)
            if m:
                try:
                    actions_str = m.group(1)
                    actions_str = re.sub(r',\s*\]', ']', actions_str)
                    result["actions"] = json.loads(actions_str)
                except Exception:
                    result["actions"] = []
            
            if result.get("intent") or result.get("message"):
                logger.logger.info("JSON healing: recovered via manual extraction")
                return result
            
            return None
        except Exception:
            return None

json_parser = JSONHealingParser()
