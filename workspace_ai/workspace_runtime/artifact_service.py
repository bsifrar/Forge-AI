from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


class ArtifactService:
    def __init__(self, *, preview_chars: int = 1200, max_bytes: int = 64_000) -> None:
        self.preview_chars = max(200, int(preview_chars))
        self.max_bytes = max(1024, int(max_bytes))

    def normalize_inputs(self, files: List[Any] | None) -> List[Dict[str, Any]]:
        artifacts: List[Dict[str, Any]] = []
        for raw in files or []:
            normalized = self._normalize_input(raw)
            if normalized is not None:
                artifacts.append(normalized)
        return artifacts

    def prompt_context(self, artifacts: List[Dict[str, Any]] | None) -> str:
        rows: List[str] = []
        for artifact in artifacts or []:
            if not isinstance(artifact, dict):
                continue
            label = str(artifact.get("label") or artifact.get("path") or "artifact").strip()
            path = str(artifact.get("path") or "").strip()
            exists = bool(artifact.get("exists"))
            kind = str(artifact.get("kind") or "unknown").strip()
            preview = str(artifact.get("preview") or "").strip()
            status = "available" if exists else "missing"
            rows.append(f"- {label} [{kind}, {status}] {path}".strip())
            if preview:
                rows.append(f"  Preview: {preview}")
        return "\n".join(rows) or "- [none]"

    def _artifact_record(self, raw_path: str) -> Dict[str, Any]:
        path = Path(raw_path).expanduser()
        resolved = path.resolve(strict=False)
        exists = resolved.exists()
        is_file = exists and resolved.is_file()
        record: Dict[str, Any] = {
            "path": str(resolved),
            "label": resolved.name or raw_path,
            "exists": bool(exists),
            "kind": "missing",
            "size_bytes": 0,
            "preview": "",
        }
        if not exists:
            return record
        if not is_file:
            record["kind"] = "directory"
            return record
        record["size_bytes"] = int(resolved.stat().st_size)
        preview, kind = self._read_preview(resolved)
        record["preview"] = preview
        record["kind"] = kind
        return record

    def _read_preview(self, path: Path) -> tuple[str, str]:
        raw = path.read_bytes()[: self.max_bytes]
        if b"\x00" in raw:
            return ("", "binary")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
        if len(cleaned) > self.preview_chars:
            cleaned = f"{cleaned[: self.preview_chars].rstrip()}..."
        return (cleaned, "text")

    def _normalize_input(self, raw: Any) -> Dict[str, Any] | None:
        if isinstance(raw, dict):
            label = str(raw.get("label") or raw.get("path") or "artifact").strip()
            path = str(raw.get("path") or label).strip()
            if not label and not path:
                return None
            kind = str(raw.get("kind") or "text").strip() or "text"
            preview = str(raw.get("preview") or "").strip()
            return {
                "path": path,
                "label": label or path,
                "exists": bool(raw.get("exists", True)),
                "kind": kind,
                "size_bytes": int(raw.get("size_bytes") or 0),
                "preview": preview[: self.preview_chars],
            }
        candidate = str(raw or "").strip()
        if not candidate:
            return None
        return self._artifact_record(candidate)
