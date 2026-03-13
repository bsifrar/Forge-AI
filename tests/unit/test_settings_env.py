from __future__ import annotations

from workspace_ai.app.settings import get_settings


def test_explicit_env_overrides_workspace_files(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_ADAPTER_MODE", "null")
    monkeypatch.setenv("WORKSPACE_EXTERNAL_BASE_URL", "http://example.invalid:9999")
    monkeypatch.setenv("WORKSPACE_HOST", "0.0.0.0")
    monkeypatch.setenv("WORKSPACE_PORT", "9001")
    monkeypatch.setenv("WORKSPACE_PROVIDER", "xai")
    monkeypatch.setenv("WORKSPACE_MODEL", "override-model")
    monkeypatch.setenv("WORKSPACE_API_KEY", "secret-from-shell")
    monkeypatch.setenv("WORKSPACE_XAI_API_KEY", "xai-secret-from-shell")

    settings = get_settings()

    assert settings.adapter_mode == "null"
    assert settings.external_base_url == "http://example.invalid:9999"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9001
    assert settings.default_provider == "xai"
    assert settings.default_model == "override-model"
    assert settings.openai_api_key == "secret-from-shell"
    assert settings.xai_api_key == "xai-secret-from-shell"
