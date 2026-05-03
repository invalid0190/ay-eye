"""
RAG Ingestor — writes documents into ChromaDB collections.

Uses content-hash–based IDs for natural deduplication: ingesting the same
content twice is a no-op (upsert).  Metadata values are sanitised to types
ChromaDB accepts (str, int, float, bool).
"""

import datetime
import hashlib
from core.rag.document_store import document_store
from core.utils.logger import logger

# Map doc_type → ChromaDB collection name
_COLLECTION_MAP = {
    "skill": "ayeye_skills",
    "app_rule": "ayeye_app_rules",
    "past_failure": "ayeye_past_failures",
    "project_knowledge": "ayeye_project_knowledge",
    "user_preference": "ayeye_user_preferences",
    "safety_rule": "ayeye_safety_rules",
    "activity": "ayeye_activity_log",
}


class Ingestor:
    """Writes structured documents into the correct ChromaDB collection."""

    def add_document(
        self,
        doc_type: str,
        title: str,
        content: str,
        tags: list | None = None,
        source: str = "manual",
        metadata: dict | None = None,
    ) -> bool:
        """Upsert a document.  Returns True on success."""
        coll_name = _COLLECTION_MAP.get(doc_type)
        if not coll_name:
            logger.logger.error(f"RAG: Unknown doc_type '{doc_type}'")
            return False

        collection = document_store.get_collection(coll_name)
        if collection is None:
            return False

        # Content-hash ID guarantees dedup across restarts
        content_hash = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()
        doc_id = f"{doc_type}_{content_hash}"

        now = datetime.datetime.now().isoformat()

        meta: dict = {
            "id": doc_id,
            "type": doc_type,
            "title": title,
            "source": source,
            "created_at": now,
            "updated_at": now,
            "tags": ",".join(tags) if tags else "",
        }
        if metadata:
            meta.update(metadata)

        # ChromaDB only accepts str | int | float | bool metadata values.
        # Drop None / list / dict to avoid runtime crashes.
        meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}

        try:
            collection.upsert(ids=[doc_id], documents=[content], metadatas=[meta])
            logger.log_event("RAG_DOCUMENT_ADDED", {"type": doc_type, "title": title[:80]})
            return True
        except Exception as e:
            logger.logger.error(f"RAG: Failed to upsert document: {e}")
            return False


ingestor = Ingestor()
