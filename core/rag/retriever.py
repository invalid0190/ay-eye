from core.rag.document_store import document_store
from core.config import sys_config
from core.utils.logger import logger
import json

class Retriever:
    def __init__(self):
        self.default_collections = [
            "ayeye_skills",
            "ayeye_app_rules",
            "ayeye_past_failures",
            "ayeye_project_knowledge",
            "ayeye_user_preferences",
            "ayeye_safety_rules"
        ]

    def search(self, query, collections=None, top_k=None, min_score=None):
        if not sys_config.get("rag_enabled"):
            return []

        collections = collections or self.default_collections
        top_k = top_k or sys_config.get("rag_top_k") or 5
        
        results = []
        for coll_name in collections:
            collection = document_store.get_collection(coll_name)
            if collection is None:
                continue
                
            try:
                # ChromaDB search
                res = collection.query(
                    query_texts=[query],
                    n_results=top_k
                )
                
                if res and res['documents'] and res['documents'][0]:
                    for i in range(len(res['documents'][0])):
                        doc = res['documents'][0][i]
                        metadata = res['metadatas'][0][i]
                        # In a real RAG we might check distance/score here
                        results.append({
                            "content": doc,
                            "metadata": metadata,
                            "type": metadata.get("type", "unknown"),
                            "title": metadata.get("title", "Untitled")
                        })
            except Exception as e:
                logger.logger.error(f"RAG: Search failed in {coll_name}: {e}")
                
        return results

    def build_context(self, query, active_app=None, active_window=None, max_chars=None):
        if not sys_config.get("rag_enabled"):
            return ""

        max_chars = max_chars or sys_config.get("rag_max_context_chars") or 3500
        
        # Enhanced query
        search_query = query
        if active_app:
            search_query += f" {active_app}"
        if active_window:
            search_query += f" {active_window}"
            
        results = self.search(search_query)
        
        if not results:
            return ""
            
        context_parts = ["--- RELEVANT MEMORY / RAG CONTEXT ---"]
        current_len = len(context_parts[0])
        
        # Deduplicate results by content hash or title/content
        seen = set()
        
        for res in results:
            content = res["content"]
            title = res["title"]
            doc_type = res["type"]
            source = res["metadata"].get("source", "unknown")
            
            # Simple dedup
            if content in seen:
                continue
            seen.add(content)
            
            block = f"\n[{doc_type}] Title: {title}\n"
            if doc_type == "past_failure":
                block += f"Previous failure: {res['metadata'].get('failure_reason', 'N/A')}\n"
                if res['metadata'].get('fix'):
                    block += f"Fix: {res['metadata'].get('fix')}\n"
            else:
                block += f"Content: {content}\n"
            
            block += f"Source: {source}\n"
            
            if current_len + len(block) > max_chars:
                break
                
            context_parts.append(block)
            current_len += len(block)
            
        context_parts.append("\n--- END RAG CONTEXT ---")
        
        if len(context_parts) <= 2: # Only headers/footers
            return ""
            
        return "".join(context_parts)

retriever = Retriever()
