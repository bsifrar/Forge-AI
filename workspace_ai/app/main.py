from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path


def _path_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _size_warning(bytes_value: int, *, warn_at: int, critical_at: int, label: str) -> str | None:
    if bytes_value >= critical_at:
        return f"critical: {label} exceeds {critical_at // (1024 * 1024)} MB"
    if bytes_value >= warn_at:
        return f"warning: {label} exceeds {warn_at // (1024 * 1024)} MB"
    return None

from workspace_ai.adapters.null_adapter import NullAdapter
from workspace_ai.adapters.external_adapter import ExternalAdapter
from workspace_ai.app.settings import get_settings
from workspace_ai.workspace_api.router import build_router
from workspace_ai.workspace_runtime.session_manager import SessionManager


def build_app() -> FastAPI:
    settings = get_settings()
    adapter = ExternalAdapter(settings.external_base_url) if settings.adapter_mode == "external" else NullAdapter()
    manager = SessionManager(adapter=adapter)
    app = FastAPI(title="Forge-AI", version="0.1.0")
    app.include_router(build_router(manager))

    @app.get("/", response_class=HTMLResponse)
    def root() -> str:
        return (Path(__file__).resolve().parents[1] / "ui" / "index.html").read_text(encoding="utf-8")

    @app.get("/health")
    def health() -> dict:
        return {
            "service": "forge-ai",
            "tagline": "Persistent AI Engineering Workspace",
            "adapter_mode": settings.adapter_mode,
            "external_base_url": settings.external_base_url if settings.adapter_mode == "external" else None,
            "storage_path": str(settings.storage_path),
        }

    @app.get("/ui", response_class=HTMLResponse)
    def ui() -> str:
        return (Path(__file__).resolve().parents[1] / "ui" / "index.html").read_text(encoding="utf-8")

    @app.get("/workspace/meta")
    def meta() -> dict:
        root = Path(__file__).resolve().parents[2]
        log_dir = root / "workspace_ai" / ".runtime_logs"
        db_size_bytes = _path_size_bytes(settings.storage_path)
        log_size_bytes = _path_size_bytes(log_dir)
        warnings = [
            warning
            for warning in [
                _size_warning(db_size_bytes, warn_at=500 * 1024 * 1024, critical_at=2 * 1024 * 1024 * 1024, label="workspace.db"),
                _size_warning(log_size_bytes, warn_at=1024 * 1024 * 1024, critical_at=5 * 1024 * 1024 * 1024, label="runtime logs"),
            ]
            if warning
        ]
        return {
            "status": "ok",
            "project_root": str(root),
            "storage_path": str(settings.storage_path),
            "storage_size_bytes": db_size_bytes,
            "runtime_log_path": str(log_dir),
            "runtime_log_size_bytes": log_size_bytes,
            "size_warnings": warnings,
            "env_workspace_path": str(root / ".env.workspace"),
            "env_secret_path": str(root / ".env.workspace.secret"),
            "default_launch": "./workspace.sh start",
            "external_launch": "WORKSPACE_ADAPTER_MODE=external ./workspace.sh start",
        }

    return app


app = build_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("workspace_ai.app.main:app", host=settings.host, port=settings.port, reload=False)
