"""
RAG Retriever — searches ChromaDB collections and builds LLM-ready context.

Retrieval priority:
  1. safety_rules   (always first)
  2. past_failures  (error-prevention)
  3. app_rules      (app-specific guidance)
  4. skills / project_knowledge / user_preferences

Results are deduplicated by content hash, distance-filtered, and truncated
to a configurable character budget so they never blow up the prompt.
"""

import hashlib
from core.rag.document_store import document_store
from core.config import sys_config
from core.utils.logger import logger

# Search order determines priority in the final context block.
_PRIORITY_COLLECTIONS = [
    "ayeye_safety_rules",
    "ayeye_past_failures",
    "ayeye_app_rules",
    "ayeye_skills",
    "ayeye_project_knowledge",
    "ayeye_user_preferences",
]

# ChromaDB uses L2 distance by default.  Higher = less relevant.
_DEFAULT_MAX_DISTANCE = 1.5


class Retriever:
    """Searches the vector store and formats context for the Brain."""

    # ------------------------------------------------------------------
    # Low-level search
    # ------------------------------------------------------------------

    def search(self, query: str, collections: list | None = None,
               top_k: int | None = None, max_distance: float | None = None) -> list[dict]:
        """Return matching documents across *collections*, ordered by priority."""
        if not sys_config.get("rag_enabled"):
            logger.log_event("RAG_SKIPPED", {"reason": "rag_enabled=false"})
            return []

        collections = collections or _PRIORITY_COLLECTIONS
        top_k = top_k or sys_config.get("rag_top_k") or 6
        max_distance = max_distance if max_distance is not None else _DEFAULT_MAX_DISTANCE

        # Limit per-collection fetch so total stays manageable
        per_collection_k = max(1, min(top_k, 3))

        logger.log_event("RAG_SEARCH_STARTED", {"query": query[:120], "collections": len(collections)})

        results: list[dict] = []
        seen_hashes: set[str] = set()

        for coll_name in collections:
            collection = document_store.get_collection(coll_name)
            if collection is None:
                continue

            try:
                count = collection.count()
                if count == 0:
                    continue
                # Never request more results than documents in collection
                n = min(per_collection_k, count)
                res = collection.query(
                    query_texts=[query],
                    n_results=n,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as e:
                logger.logger.error(f"RAG: Search failed in {coll_name}: {e}")
                continue

            if not res or not res.get("documents") or not res["documents"][0]:
                continue

            docs = res["documents"][0]
            metas = res["metadatas"][0]
            dists = res.get("distances", [[]])[0]

            for i, doc in enumerate(docs):
                dist = dists[i] if i < len(dists) else 999
                if dist > max_distance:
                    continue

                # Deduplicate by content hash
                h = hashlib.md5(doc.encode("utf-8", errors="replace")).hexdigest()
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

                meta = metas[i] if i < len(metas) else {}
                results.append({
                    "content": doc,
                    "metadata": meta,
                    "type": meta.get("type", "unknown"),
                    "title": meta.get("title", "Untitled"),
                    "distance": dist,
                })

        logger.log_event("RAG_RESULTS_COUNT", {"count": len(results)})
        return results

    # ------------------------------------------------------------------
    # Context builder
    # ------------------------------------------------------------------

    def build_context(self, query: str, active_app: str | None = None,
                      active_window: str | None = None,
                      max_chars: int | None = None) -> str:
        """Build a formatted context string ready for prompt injection."""
        if not sys_config.get("rag_enabled"):
            return ""

        max_chars = max_chars or sys_config.get("rag_max_context_chars") or 3500

        # Enrich query with app/window for better relevance
        parts = [query]
        if active_app:
            parts.append(active_app)
        if active_window:
            parts.append(active_window)
        search_query = " ".join(parts)

        try:
            results = self.search(search_query)
        except Exception as e:
            logger.logger.error(f"RAG: build_context search failed: {e}")
            logger.log_event("RAG_SKIPPED", {"reason": str(e)[:200]})
            return ""

        if not results:
            return ""

        header = "--- RELEVANT MEMORY / RAG CONTEXT ---"
        footer = "\n--- END RAG CONTEXT ---"
        context_parts = [header]
        budget = max_chars - len(header) - len(footer)

        for res in results:
            content = res["content"]
            title = res["title"]
            doc_type = res["type"]
            source = res["metadata"].get("source", "unknown")

            # Build block
            block_lines = [f"\n[{doc_type}] Title: {title}"]
            if doc_type == "past_failure":
                reason = res["metadata"].get("failure_reason", "N/A")
                block_lines.append(f"Previous failure: {reason[:300]}")
                fix = res["metadata"].get("fix")
                if fix:
                    block_lines.append(f"Fix: {fix[:200]}")
            else:
                # Truncate individual doc content to keep prompt lean
                block_lines.append(f"Content: {content[:400]}")
            block_lines.append(f"Source: {source}")
            block = "\n".join(block_lines) + "\n"

            if len(block) > budget:
                break

            context_parts.append(block)
            budget -= len(block)

        if len(context_parts) <= 1:  # Only the header
            return ""

        context_parts.append(footer)
        built = "".join(context_parts)
        logger.log_event("RAG_CONTEXT_BUILT", {"chars": len(built), "docs": len(context_parts) - 2})
        return built


retriever = Retriever()
