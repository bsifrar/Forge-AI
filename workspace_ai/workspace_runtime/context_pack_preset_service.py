from __future__ import annotations

from typing import Any, Dict, List

from workspace_ai.workspace_memory.session_store import SessionStore


class ContextPackPresetService:
    def __init__(self, *, store: SessionStore) -> None:
        self.store = store

    def create(self, *, project_id: str, name: str, import_ids: List[str]) -> Dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("preset name is required")
        valid_ids = self._filter_valid_ids(project_id=project_id, import_ids=import_ids)
        preset = self.store.create_context_pack_preset(project_id=project_id, name=name, import_ids=valid_ids)
        return {"status": "ok", "preset": preset}

    def list_presets(self, *, project_id: str | None = None) -> Dict[str, Any]:
        presets = self.store.list_context_pack_presets(project_id=project_id)
        return {"status": "ok", "count": len(presets), "presets": presets}

    def get(self, *, preset_id: str) -> Dict[str, Any]:
        preset = self.store.get_context_pack_preset(preset_id)
        if preset is None:
            return {"status": "not_found", "preset_id": preset_id}
        return {"status": "ok", "preset": preset}

    def apply(self, *, preset_id: str, project_id: str) -> Dict[str, Any]:
        """Return the preset's import IDs, silently filtering any that no longer exist in project."""
        preset = self.store.get_context_pack_preset(preset_id)
        if preset is None:
            return {"status": "not_found", "preset_id": preset_id}
        raw_ids: List[str] = preset.get("import_ids") or []
        valid_ids = self._filter_valid_ids(project_id=project_id, import_ids=raw_ids)
        return {
            "status": "ok",
            "preset_id": preset_id,
            "preset_name": preset["name"],
            "import_ids": valid_ids,
            "filtered_count": len(raw_ids) - len(valid_ids),
        }

    def update(self, *, preset_id: str, name: str | None = None, import_ids: List[str] | None = None) -> Dict[str, Any]:
        existing = self.store.get_context_pack_preset(preset_id)
        if existing is None:
            return {"status": "not_found", "preset_id": preset_id}
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("preset name cannot be empty")
        if import_ids is not None:
            import_ids = self._filter_valid_ids(project_id=existing["project_id"], import_ids=import_ids)
        updated = self.store.update_context_pack_preset(preset_id=preset_id, name=name, import_ids=import_ids)
        return {"status": "ok", "preset": updated}

    def delete(self, *, preset_id: str) -> Dict[str, Any]:
        deleted = self.store.delete_context_pack_preset(preset_id=preset_id)
        return {"status": "ok" if deleted else "not_found", "preset_id": preset_id}

    def _filter_valid_ids(self, *, project_id: str, import_ids: List[str]) -> List[str]:
        """Return only those import_ids that exist and belong to project_id."""
        valid: List[str] = []
        for import_id in import_ids:
            item = self.store.get_context_import(import_id)
            if item is not None and item["project_id"] == project_id:
                valid.append(import_id)
        return valid
