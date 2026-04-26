from typing import List, Dict, Any

class ShortTermMemory:
    def __init__(self, capacity=5):
        self.history: List[Dict[str, Any]] = []
        self.capacity = capacity

    def add(self, user_text: str, ai_response: Dict[str, Any]):
        self.history.append({
            "user": user_text,
            "assistant_message": ai_response.get("message", ""),
            "actions_taken": ai_response.get("actions", [])
        })
        if len(self.history) > self.capacity:
            self.history.pop(0)

    def get_history_string(self) -> str:
        if not self.history:
            return "No recent conversation history."
        
        result = []
        for i, turn in enumerate(self.history):
            result.append(f"[Turn {i+1}]")
            result.append(f"User: {turn['user']}")
            result.append(f"Assistant: {turn['assistant_message']}")
            if turn['actions_taken']:
                result.append(f"Actions Taken: {turn['actions_taken']}")
        return "\n".join(result)

short_term_memory = ShortTermMemory()
