import os
import chromadb
from chromadb.config import Settings
from core.config import sys_config
from core.utils.logger import logger

class DocumentStore:
    def __init__(self):
        self.client = None
        self.collections = {}
        self.persist_path = sys_config.get("rag_persist_path") or "data/rag/chroma"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
        os.makedirs(self.persist_path, exist_ok=True)

    def _get_client(self):
        if self.client is None:
            try:
                self.client = chromadb.PersistentClient(path=self.persist_path)
                logger.logger.info(f"RAG: ChromaDB initialized at {self.persist_path}")
            except Exception as e:
                logger.logger.error(f"RAG: Failed to initialize ChromaDB: {e}")
                return None
        return self.client

    def get_collection(self, name):
        client = self._get_client()
        if client is None:
            return None
            
        if name not in self.collections:
            try:
                self.collections[name] = client.get_or_create_collection(name=name)
            except Exception as e:
                logger.logger.error(f"RAG: Failed to get/create collection {name}: {e}")
                return None
        return self.collections[name]

document_store = DocumentStore()
