"""
RAG Manager — public API for the Ay-Eye RAG subsystem.

All other modules should interact with RAG exclusively through this
singleton.  It delegates to Ingestor (writes) and Retriever (reads) and
adds domain-specific convenience methods for failure/success recording.
"""

import hashlib
from core.rag.ingest import ingestor
from core.rag.retriever import retriever
from core.utils.logger import logger


class RagManager:
    """Facade over the RAG ingest + retrieval pipeline."""

    def __init__(self):
        # Track recently written content hashes to avoid spamming the DB
        # inside a single session (e.g. Blender rule written 50 times).
        self._recent_writes: set[str] = set()
        self._MAX_RECENT = 256

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def add_document(self, doc_type, title, content, tags=None, source="manual", metadata=None):
        """Upsert a document.  Skipped if identical content was written this session."""
        h = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()
        if h in self._recent_writes:
            return True  # Already stored this session — no-op
        result = ingestor.add_document(doc_type, title, content, tags, source, metadata)
        if result:
            self._recent_writes.add(h)
            if len(self._recent_writes) > self._MAX_RECENT:
                # Evict oldest half to cap memory
                self._recent_writes = set(list(self._recent_writes)[self._MAX_RECENT // 2:])
        return result

    def search(self, query, collections=None, top_k=5, max_distance=None):
        """Search across collections."""
        return retriever.search(query, collections, top_k, max_distance)

    def build_context(self, query, active_app=None, active_window=None, max_chars=3500):
        """Build formatted RAG context for injection into the LLM prompt."""
        return retriever.build_context(query, active_app, active_window, max_chars)

    # ------------------------------------------------------------------
    # Domain helpers
    # ------------------------------------------------------------------

    def remember_failure(self, command, app, window, failure_reason, fix=None):
        """Record a failed action so the AI can avoid repeating the mistake."""
        title = f"Failure: {command[:60]}"
        content = f"Command '{command}' failed in {app} ({window}). Reason: {failure_reason}"
        metadata = {
            "command": str(command)[:200],
            "app": str(app),
            "window": str(window),
            "failure_reason": str(failure_reason)[:500],
        }
        if fix:
            metadata["fix"] = str(fix)[:300]
        return self.add_document(
            "past_failure", title, content,
            tags=[app, "failure"], source="auto_error", metadata=metadata,
        )

    def remember_success(self, command, app, window, summary):
        """Record a meaningful success for reinforcement."""
        title = f"Success: {command[:60]}"
        content = f"Successfully executed '{command}' in {app}. Summary: {summary}"
        metadata = {
            "command": str(command)[:200],
            "app": str(app),
            "window": str(window),
            "summary": str(summary)[:300],
        }
        return self.add_document(
            "project_knowledge", title, content,
            tags=[app, "success"], source="auto_success", metadata=metadata,
        )

    def add_app_rule(self, app, rule, tags=None):
        """Store an application-specific behavioural rule."""
        title = f"Rule for {app}"
        tags = list(tags or [])
        if app not in tags:
            tags.append(app)
        return self.add_document("app_rule", title, rule, tags=tags, source="auto_rule")

    def add_skill(self, name, instruction, tags=None):
        """Persist a learned skill/workflow."""
        return self.add_document("skill", name, instruction, tags=tags, source="manual")


rag_manager = RagManager()
