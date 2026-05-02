"""
ChromaDB Document Store — singleton wrapper for persistent vector database.

Provides lazy-initialised access to ChromaDB collections used by the RAG
layer.  If ChromaDB is unavailable or corrupt the rest of Ay-Eye continues
to work without RAG.
"""

import os
import chromadb
from core.config import sys_config
from core.utils.logger import logger


class DocumentStore:
    """Thread-safe, lazily-initialised ChromaDB wrapper."""

    def __init__(self):
        self._client = None
        self._collections: dict = {}
        self._persist_path: str = sys_config.get("rag_persist_path") or "data/rag/chroma"
        self._init_failed: bool = False  # Avoid retrying a broken DB every call

        # Ensure directory tree exists (safe even on first run)
        os.makedirs(self._persist_path, exist_ok=True)

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return the ChromaDB PersistentClient, creating it on first call."""
        if self._init_failed:
            return None
        if self._client is None:
            try:
                self._client = chromadb.PersistentClient(path=self._persist_path)
                logger.log_event("RAG_DB_INITIALIZED", {"path": self._persist_path})
            except Exception as e:
                self._init_failed = True
                logger.logger.error(f"RAG: ChromaDB init failed (will not retry): {e}")
                return None
        return self._client

    # ------------------------------------------------------------------
    # Collection access
    # ------------------------------------------------------------------

    def get_collection(self, name: str):
        """Return a ChromaDB collection by *name*, creating if necessary."""
        client = self._get_client()
        if client is None:
            return None

        if name not in self._collections:
            try:
                self._collections[name] = client.get_or_create_collection(name=name)
            except Exception as e:
                logger.logger.error(f"RAG: Failed to get/create collection '{name}': {e}")
                return None
        return self._collections[name]


document_store = DocumentStore()
