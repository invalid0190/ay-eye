from core.rag.ingest import ingestor
from core.rag.retriever import retriever
from core.utils.logger import logger

class RagManager:
    def add_document(self, doc_type, title, content, tags=None, source="manual", metadata=None):
        return ingestor.add_document(doc_type, title, content, tags, source, metadata)

    def search(self, query, collections=None, top_k=5, min_score=None):
        return retriever.search(query, collections, top_k, min_score)

    def build_context(self, query, active_app=None, active_window=None, max_chars=3500):
        return retriever.build_context(query, active_app, active_window, max_chars)

    def remember_failure(self, command, app, window, failure_reason, fix=None):
        title = f"Failure: {command[:50]}"
        content = f"Command '{command}' failed in {app} ({window}). Reason: {failure_reason}"
        metadata = {
            "command": command,
            "app": app,
            "window": window,
            "failure_reason": failure_reason,
            "fix": fix
        }
        return self.add_document("past_failure", title, content, tags=[app, "failure"], source="auto_error", metadata=metadata)

    def remember_success(self, command, app, window, summary):
        title = f"Success: {command[:50]}"
        content = f"Successfully executed '{command}' in {app}. Summary: {summary}"
        metadata = {
            "command": command,
            "app": app,
            "window": window,
            "summary": summary
        }
        # Successes might be project_knowledge or just a new type if we wanted, but project_knowledge fits
        return self.add_document("project_knowledge", title, content, tags=[app, "success"], source="auto_success", metadata=metadata)

    def add_app_rule(self, app, rule, tags=None):
        title = f"Rule for {app}"
        tags = tags or []
        if app not in tags:
            tags.append(app)
        return self.add_document("app_rule", title, rule, tags=tags, source="auto_rule")

    def add_skill(self, name, instruction, tags=None):
        return self.add_document("skill", name, instruction, tags=tags, source="manual")

rag_manager = RagManager()
