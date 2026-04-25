import chromadb
from chromadb.config import Settings
import time
from typing import List, Dict, Any, Optional
from core.utils.logger import logger

class MemoryManager:
    def __init__(self, db_path="./.ay-eye-memory"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name="ay_eye_memory")

    def store(self, app: str, context: str, response: Dict[str, Any], score: float = 1.0):
        # Store only meaningful interactions
        if response.get("confidence", 0) < 0.7:
            return

        try:
            self.collection.add(
                documents=[context],
                metadatas=[{
                    "app": app,
                    "intent": response.get("intent", ""),
                    "score": score,
                    "timestamp": time.time(),
                    "usage_count": 1
                }],
                ids=[f"mem_{int(time.time()*1000)}"]
            )
            logger.log_event("MEMORY_STORED", {"app": app, "intent": response.get("intent")})
        except Exception as e:
            logger.logger.error(f"Memory store error: {e}")

    def retrieve(self, app: str, query: str, limit: int = 3) -> List[str]:
        try:
            # Hybrid: filter by app then semantic search
            results = self.collection.query(
                query_texts=[query],
                where={"app": app},
                n_results=limit
            )
            return results.get("documents", [[]])[0]
        except Exception as e:
            logger.logger.error(f"Memory retrieve error: {e}")
            return []

memory_manager = MemoryManager()
