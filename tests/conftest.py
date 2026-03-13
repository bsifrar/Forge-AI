from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def isolated_workspace_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    storage_path = tmp_path / "workspace.db"
    for key in [
        "WORKSPACE_STORAGE_PATH",
        "WORKSPACE_ADAPTER_MODE",
        "WORKSPACE_EXTERNAL_BASE_URL",
        "WORKSPACE_HOST",
        "WORKSPACE_PORT",
        "WORKSPACE_PROVIDER",
        "WORKSPACE_MODEL",
        "WORKSPACE_API_KEY",
        "WORKSPACE_OPENAI_API_KEY",
        "WORKSPACE_XAI_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "XAI_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(storage_path))
    monkeypatch.setenv("WORKSPACE_ADAPTER_MODE", "null")
    monkeypatch.setenv("WORKSPACE_HOST", "127.0.0.1")
    monkeypatch.setenv("WORKSPACE_PORT", "8091")
    monkeypatch.setenv("WORKSPACE_PROVIDER", "openai")
    monkeypatch.setenv("WORKSPACE_MODEL", "test-model")
    monkeypatch.setenv("WORKSPACE_API_KEY", "")
    monkeypatch.setenv("WORKSPACE_OPENAI_API_KEY", "")
    monkeypatch.setenv("WORKSPACE_XAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("XAI_API_KEY", "")
    return storage_path
