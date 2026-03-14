from __future__ import annotations

from typing import Any, Dict, List

from workspace_ai.workspace_memory.session_store import SessionStore

_CATEGORY_LABEL: Dict[str, str] = {
    "preference": "User Preference",
    "project_background": "Project Background",
    "reference": "Reference",
    "transient": "Transient Note",
}


class ContextImportService:
    def __init__(self, *, store: SessionStore | None = None) -> None:
        self.store = store or SessionStore()

    def create(
        self,
        *,
        project_id: str,
        source_label: str,
        content: str,
        category: str = "reference",
    ) -> Dict[str, Any]:
        return self.store.create_context_import(
            project_id=project_id,
            source_label=source_label,
            content=content,
            category=category,
        )

    def list_imports(self, *, project_id: str | None = None, limit: int = 200) -> Dict[str, Any]:
        items = self.store.list_context_imports(project_id=project_id, limit=limit)
        return {"status": "ok", "count": len(items), "imports": items}

    def set_enabled(self, *, import_id: str, enabled: bool) -> Dict[str, Any]:
        item = self.store.set_context_import_enabled(import_id=import_id, enabled=enabled)
        if item is None:
            return {"status": "not_found", "import_id": import_id}
        return {"status": "ok", "import": item}

    def delete(self, *, import_id: str) -> Dict[str, Any]:
        deleted = self.store.delete_context_import(import_id=import_id)
        return {"status": "ok" if deleted else "not_found", "import_id": import_id}

    def build_context_block(self, *, project_id: str) -> str:
        """Return a labelled text block of all enabled imports for injection into prompts."""
        items = self.store.list_enabled_context_imports(project_id=project_id)
        if not items:
            return ""
        lines: List[str] = ["Imported context:"]
        for item in items:
            label = _CATEGORY_LABEL.get(item["category"], item["category"])
            source = item["source_label"] or item["import_id"]
            lines.append(f"[{label} — {source}]\n{item['content'].strip()}")
        return "\n\n".join(lines)
