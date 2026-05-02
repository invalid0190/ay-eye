import uuid
import datetime
import hashlib
from core.rag.document_store import document_store
from core.utils.logger import logger

class Ingestor:
    def add_document(self, doc_type, title, content, tags=None, source="manual", metadata=None):
        collection_name = f"ayeye_{doc_type}s"
        if not collection_name.endswith("s"): # Handle plurals if needed, but the spec says specific names
            pass
            
        # Mapping to spec collection names
        mapping = {
            "skill": "ayeye_skills",
            "app_rule": "ayeye_app_rules",
            "past_failure": "ayeye_past_failures",
            "project_knowledge": "ayeye_project_knowledge",
            "user_preference": "ayeye_user_preferences",
            "safety_rule": "ayeye_safety_rules"
        }
        
        coll_name = mapping.get(doc_type)
        if not coll_name:
            logger.logger.error(f"RAG: Unknown doc_type {doc_type}")
            return False
            
        collection = document_store.get_collection(coll_name)
        if not collection:
            return False
            
        # Create a unique ID if not provided, or use content hash for dedup
        content_hash = hashlib.md5(content.encode()).hexdigest()
        doc_id = f"{doc_type}_{content_hash}"
        
        now = datetime.datetime.now().isoformat()
        
        meta = {
            "id": doc_id,
            "type": doc_type,
            "title": title,
            "source": source,
            "created_at": now,
            "updated_at": now,
            "tags": ",".join(tags) if tags else ""
        }
        if metadata:
            meta.update(metadata)
            
        try:
            # Upsert in ChromaDB
            collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[meta]
            )
            logger.logger.info(f"RAG: Added/Updated {doc_type}: {title}")
            return True
        except Exception as e:
            logger.logger.error(f"RAG: Failed to add document: {e}")
            return False

ingestor = Ingestor()
