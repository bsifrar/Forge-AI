from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.debate_service import DebateService
from workspace_ai.workspace_runtime.settings_service import SettingsService
from workspace_ai.workspace_runtime.stream_manager import StreamManager


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


class _CaptureProvider:
    def __init__(self, *, provider_name: str, content: str, prompts: List[str]) -> None:
        self.provider_name = provider_name
        self.content = content
        self.prompts = prompts

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation: List[Dict[str, str]] | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> Dict[str, Any]:
        self.prompts.append(user_prompt)
        return {
            "content": self.content,
            "provider": self.provider_name,
            "model": model or "test-model",
            "mode": "mock",
            "usage": {},
        }


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

    result = service.start_debate(project_id="forge", topic="All providers fail", max_rounds=2, _sync=True)
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
        _sync=True,
    )
    debate = result["debate"]
    assert result["status"] == "ok"
    assert debate["status"] == "max_rounds"
    assert len(debate["rounds"]) == 2
    assert any((round_item.get("response") or {}).get("mode") == "error" for round_item in debate["rounds"])
    assert debate["final_plan"]["structured"]["plan"] == "openai response"
    assert any("xai timeout" in warning for warning in debate["final_plan"].get("warnings", []))


def test_debate_service_normalizes_structured_rounds_and_final_plan(monkeypatch, isolated_workspace_env):
    service = _debate_service(isolated_workspace_env)

    def fake_get_provider(provider_name: str, *, api_key: str | None = None, model: str | None = None):
        if provider_name == "openai":
            return _MockProvider(
                provider_name=provider_name,
                content='{"proposal":"Use a bounded JSON debate loop.","rationale":"It is easier to parse and judge.","risks":["Schema drift"],"confidence":0.82,"agreed":true}',
            )
        return _MockProvider(
            provider_name=provider_name,
            content='{"plan":"Use a bounded JSON debate loop.","rationale":"Both providers converged on structured output.","risks":["Need migration for old rows"],"confidence":0.77,"agreed":true}',
        )

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(
        project_id="forge",
        topic="Structured debate output",
        participants=[{"provider": "openai", "model": "test-model"}],
        max_rounds=2,
        judge_provider="xai",
        _sync=True,
    )

    debate = result["debate"]
    round_payload = debate["rounds"][0]["response"]["structured"]
    final_payload = debate["final_plan"]["structured"]

    assert debate["status"] == "completed"
    assert round_payload["proposal"] == "Use a bounded JSON debate loop."
    assert round_payload["risks"] == ["Schema drift"]
    assert round_payload["agreed"] is True
    assert final_payload["plan"] == "Use a bounded JSON debate loop."
    assert final_payload["risks"] == ["Need migration for old rows"]
    assert "Confidence: 0.77" in debate["final_plan"]["content"]


def test_debate_service_includes_local_artifact_previews(monkeypatch, isolated_workspace_env, tmp_path):
    service = _debate_service(isolated_workspace_env)
    artifact_path = tmp_path / "sample_module.py"
    artifact_path.write_text("def run():\n    return 'forge'\n", encoding="utf-8")
    prompts: List[str] = []

    def fake_get_provider(provider_name: str, *, api_key: str | None = None, model: str | None = None):
        if provider_name == "openai":
            return _CaptureProvider(
                provider_name=provider_name,
                prompts=prompts,
                content='{"proposal":"Inspect sample_module.py before editing.","rationale":"The preview shows the current implementation.","risks":[],"confidence":0.7,"agreed":true}',
            )
        return _MockProvider(
            provider_name=provider_name,
            content='{"plan":"Inspect sample_module.py before editing.","rationale":"The artifact preview grounded the decision.","risks":[],"confidence":0.7,"agreed":true}',
        )

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(
        project_id="forge",
        topic="Use local file context",
        files=[str(artifact_path)],
        participants=[{"provider": "openai", "model": "test-model"}],
        judge_provider="xai",
        max_rounds=1,
        _sync=True,
    )

    debate = result["debate"]
    assert debate["files"][0]["exists"] is True
    assert debate["files"][0]["kind"] == "text"
    assert "sample_module.py" in debate["files"][0]["path"]
    assert "def run()" in debate["files"][0]["preview"]
    assert prompts
    assert "Artifacts:" in prompts[0]
    assert "Preview: def run():" in prompts[0]


def test_debate_service_accepts_prebuilt_artifact_payloads(monkeypatch, isolated_workspace_env):
    service = _debate_service(isolated_workspace_env)
    prompts: List[str] = []

    def fake_get_provider(provider_name: str, *, api_key: str | None = None, model: str | None = None):
        if provider_name == "openai":
            return _CaptureProvider(
                provider_name=provider_name,
                prompts=prompts,
                content='{"proposal":"Use uploaded browser artifact preview.","rationale":"The artifact preview is already embedded.","risks":[],"confidence":0.71,"agreed":true}',
            )
        return _MockProvider(
            provider_name=provider_name,
            content='{"plan":"Use uploaded browser artifact preview.","rationale":"The preview grounded the plan.","risks":[],"confidence":0.71,"agreed":true}',
        )

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(
        project_id="forge",
        topic="Browser-selected file context",
        files=[
            {
                "path": "notes.txt",
                "label": "notes.txt",
                "exists": True,
                "kind": "text",
                "size_bytes": 42,
                "preview": "Uploaded from the browser picker.",
            }
        ],
        participants=[{"provider": "openai", "model": "test-model"}],
        judge_provider="xai",
        max_rounds=1,
        _sync=True,
    )

    debate = result["debate"]
    assert debate["files"][0]["label"] == "notes.txt"
    assert debate["files"][0]["preview"] == "Uploaded from the browser picker."
    assert prompts
    assert "Preview: Uploaded from the browser picker." in prompts[0]


# ── async execution tests ──────────────────────────────────────────────────────

def _wait_terminal(store, debate_id, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        d = store.get_debate(debate_id)
        if d and d.get("status") not in {"pending", "running"}:
            return d
        time.sleep(0.02)
    return store.get_debate(debate_id)


def test_start_debate_returns_running_immediately(monkeypatch, isolated_workspace_env):
    """start_debate returns {status: running} before background thread finishes."""
    store = SessionStore(db_path=str(isolated_workspace_env))
    settings_service = SettingsService(store=store)
    stream_manager = StreamManager()
    service = DebateService(store=store, settings_service=settings_service, stream_manager=stream_manager)

    def fake_get_provider(provider_name, *, api_key=None, model=None):
        return _MockProvider(provider_name=provider_name, content='{"proposal":"p","rationale":"r","risks":[],"confidence":0.5,"agreed":true}')

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(project_id="forge", topic="Async test", max_rounds=1)
    assert result["status"] == "running"
    assert result["debate"]["debate_id"]


def test_start_debate_background_thread_completes(monkeypatch, isolated_workspace_env):
    """Background thread eventually sets debate status to completed or max_rounds."""
    store = SessionStore(db_path=str(isolated_workspace_env))
    settings_service = SettingsService(store=store)
    stream_manager = StreamManager()
    service = DebateService(store=store, settings_service=settings_service, stream_manager=stream_manager)

    def fake_get_provider(provider_name, *, api_key=None, model=None):
        return _MockProvider(provider_name=provider_name, content='{"proposal":"p","rationale":"r","risks":[],"confidence":0.5,"agreed":false}')

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(project_id="forge", topic="Background complete test", max_rounds=1)
    debate_id = result["debate"]["debate_id"]

    debate = _wait_terminal(store, debate_id)
    assert debate["status"] in {"completed", "max_rounds", "failed"}
    assert len(debate["rounds"]) >= 1


def test_start_debate_publishes_round_events(monkeypatch, isolated_workspace_env):
    """stream_manager receives round_complete and completed events from the background thread."""
    store = SessionStore(db_path=str(isolated_workspace_env))
    settings_service = SettingsService(store=store)
    stream_manager = StreamManager()
    service = DebateService(store=store, settings_service=settings_service, stream_manager=stream_manager)

    def fake_get_provider(provider_name, *, api_key=None, model=None):
        return _MockProvider(provider_name=provider_name, content='{"proposal":"p","rationale":"r","risks":[],"confidence":0.5,"agreed":false}')

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(project_id="forge", topic="Event publish test", max_rounds=1)
    debate_id = result["debate"]["debate_id"]
    _wait_terminal(store, debate_id)

    all_events = stream_manager.list_events(limit=50)["events"]
    event_types = {e["event_type"] for e in all_events}
    assert "workspace.debate.round_complete" in event_types
    assert "workspace.debate.completed" in event_types
    round_event = next(e for e in all_events if e["event_type"] == "workspace.debate.round_complete")
    assert round_event["payload"]["debate_id"] == debate_id


def test_start_debate_sync_flag_bypasses_thread(monkeypatch, isolated_workspace_env):
    """_sync=True runs synchronously and returns status 'ok' with final debate."""
    service = _debate_service(isolated_workspace_env)

    def fake_get_provider(provider_name, *, api_key=None, model=None):
        return _MockProvider(provider_name=provider_name, content='{"proposal":"p","rationale":"r","risks":[],"confidence":0.5,"agreed":false}')

    monkeypatch.setattr("workspace_ai.workspace_runtime.debate_service.get_provider", fake_get_provider)

    result = service.start_debate(project_id="forge", topic="Sync flag test", max_rounds=1, _sync=True)
    assert result["status"] == "ok"
    assert result["debate"]["status"] in {"completed", "max_rounds", "failed"}
