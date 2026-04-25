from typing import List, Dict, Any

class ShortTermMemory:
    def __init__(self, capacity=10):
        self.history: List[Dict[str, Any]] = []
        self.capacity = capacity

    def add(self, interaction: Dict[str, Any]):
        self.history.append(interaction)
        if len(self.history) > self.capacity:
            self.history.pop(0)

    def get_all(self) -> List[Dict[str, Any]]:
        return self.history

short_term_memory = ShortTermMemory()
