from __future__ import annotations

from typing import Any, Dict, List

import pytest

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.debate_service import DebateService
from workspace_ai.workspace_runtime.settings_service import SettingsService


class _MockProvider:
    def __init__(self, *, provider_name: str, content: str) -> None:
        self.provider_name = provider_name
        self.content = content

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation: List[Dict[str, str]] | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> Dict[str, Any]:
        return {
            "content": self.content,
            "provider": self.provider_name,
            "model": model or "test-model",
            "mode": "mock",
            "usage": {},
        }


class _FailProvider:
    def __init__(self, *, provider_name: str, error: str) -> None:
        self.provider_name = provider_name
        self.error = error

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation: List[Dict[str, str]] | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> Dict[str, Any]:
        raise RuntimeError(self.error)


def _debate_service(isolated_workspace_env) -> DebateService:
    store = SessionStore(db_path=str(isolated_workspace_env))
    settings_service = SettingsService(store=store)
    return DebateService(store=store, settings_service=settings_service)


def test_debate_service_rejects_unknown_participant_provider(isolated_workspace_env):
    service = _debate_service(isolated_workspace_env)
    with pytest.raises(ValueError, match="participants.provider"):
        service.start_debate(
            project_id="forge",
            topic="Provider validation",
            participants=[{"provider": "bad-provider", "model": "test-model"}],
            max_rounds=1,
        )


def test_debate_service_marks_failed_when_all_participants_error(monkeypatch, isolated_workspace_env):
    service = _debate_service(isolated_workspace_env)

    def fake_get_provider(provider_name: str, *, api_key: str | None = None, model: str | None = None):
        return _FailProvider(provider_name=provider_name, error=f"{provider_name} down")

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(project_id="forge", topic="All providers fail", max_rounds=2)
    debate = result["debate"]
    assert result["status"] == "ok"
    assert debate["status"] == "failed"
    assert len(debate["rounds"]) == 4
    assert "all participant responses errored" in debate["final_plan"]["content"].lower()
    assert len(debate["final_plan"].get("errors", [])) == 4


def test_debate_service_continues_when_one_provider_errors(monkeypatch, isolated_workspace_env):
    service = _debate_service(isolated_workspace_env)

    def fake_get_provider(provider_name: str, *, api_key: str | None = None, model: str | None = None):
        if provider_name == "xai":
            return _FailProvider(provider_name=provider_name, error="xai timeout")
        return _MockProvider(provider_name=provider_name, content="openai response")

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(
        project_id="forge",
        topic="Partial provider error",
        participants=[
            {"provider": "openai", "model": "test-model"},
            {"provider": "xai", "model": "test-model"},
        ],
        max_rounds=1,
    )
    debate = result["debate"]
    assert result["status"] == "ok"
    assert debate["status"] == "max_rounds"
    assert len(debate["rounds"]) == 2
    assert any((round_item.get("response") or {}).get("mode") == "error" for round_item in debate["rounds"])
    assert debate["final_plan"]["content"] == "openai response"
    assert any("xai timeout" in warning for warning in debate["final_plan"].get("warnings", []))
