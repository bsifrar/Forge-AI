from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from workspace_ai.app.main import build_app
from workspace_ai.workspace_runtime.debate_service import DebateService


def test_session_create_list_delete_and_meta(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    create = client.post("/workspace/sessions", json={"project_id": "workspace", "title": "API test", "mode": "chat"})
    assert create.status_code == 200
    payload = create.json()
    session_id = payload["session"]["session_id"]

    listed = client.get("/workspace/sessions", params={"project_id": "workspace"})
    assert listed.status_code == 200
    assert any(session["session_id"] == session_id for session in listed.json()["sessions"])

    meta = client.get("/workspace/meta")
    assert meta.status_code == 200
    meta_payload = meta.json()
    assert meta_payload["storage_path"].endswith("workspace.db")
    assert "storage_size_bytes" in meta_payload
    assert "runtime_log_size_bytes" in meta_payload
    assert "size_warnings" in meta_payload

    deleted = client.delete(f"/workspace/sessions/{session_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted_session_id"] == session_id


def test_settings_include_provider_selection(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    monkeypatch.setenv("WORKSPACE_PROVIDER", "xai")
    app = build_app()
    client = TestClient(app)

    settings = client.get("/workspace/settings")
    assert settings.status_code == 200
    payload = settings.json()["settings"]
    assert payload["selected_provider"] == "xai"
    assert "xai" in payload["available_providers"]


def test_debate_start_and_fetch(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    create = client.post(
        "/workspace/debates",
        json={
            "project_id": "forge",
            "topic": "How should Forge structure provider debates?",
            "bottlenecks": "Need a minimal orchestration loop",
            "participants": [
                {"provider": "openai", "model": "test-model"},
                {"provider": "xai", "model": "test-model"},
            ],
            "max_rounds": 4,
        },
    )
    assert create.status_code == 200
    payload = create.json()
    assert payload["status"] == "ok"
    debate_id = payload["debate"]["debate_id"]
    assert payload["debate"]["max_rounds"] == 4
    assert payload["debate"]["status"] in {"completed", "max_rounds"}
    assert len(payload["debate"]["rounds"]) >= 1
    assert "structured" in payload["debate"]["rounds"][0]["response"]
    assert "structured" in payload["debate"]["final_plan"]

    fetched = client.get(f"/workspace/debates/{debate_id}")
    assert fetched.status_code == 200
    assert fetched.json()["debate"]["debate_id"] == debate_id


def test_debate_artifacts_are_returned_with_metadata(monkeypatch, isolated_workspace_env, tmp_path: Path):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    artifact_path = tmp_path / "notes.txt"
    artifact_path.write_text("Forge should include local artifact previews in debates.", encoding="utf-8")
    app = build_app()
    client = TestClient(app)

    create = client.post(
        "/workspace/debates",
        json={
            "project_id": "forge",
            "topic": "Use artifact previews",
            "files": [str(artifact_path)],
            "participants": [{"provider": "openai", "model": "test-model"}],
            "max_rounds": 1,
        },
    )

    assert create.status_code == 200
    debate = create.json()["debate"]
    assert len(debate["files"]) == 1
    artifact = debate["files"][0]
    assert artifact["exists"] is True
    assert artifact["kind"] == "text"
    assert artifact["label"] == "notes.txt"
    assert "local artifact previews" in artifact["preview"]


def test_debate_accepts_browser_artifact_payloads(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    create = client.post(
        "/workspace/debates",
        json={
            "project_id": "forge",
            "topic": "Browser artifact payload",
            "files": [
                {
                    "path": "notes.txt",
                    "label": "notes.txt",
                    "exists": True,
                    "kind": "text",
                    "size_bytes": 24,
                    "preview": "Chosen from the browser.",
                }
            ],
            "participants": [{"provider": "openai", "model": "test-model"}],
            "max_rounds": 1,
        },
    )

    assert create.status_code == 200
    artifact = create.json()["debate"]["files"][0]
    assert artifact["label"] == "notes.txt"
    assert artifact["preview"] == "Chosen from the browser."


def test_debate_invalid_provider_payload(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    invalid = client.post(
        "/workspace/debates",
        json={
            "project_id": "forge",
            "topic": "Invalid provider debate",
            "participants": [{"provider": "bad-provider", "model": "test-model"}],
        },
    )
    assert invalid.status_code == 422


def test_debate_empty_participants_uses_defaults(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    created = client.post(
        "/workspace/debates",
        json={
            "project_id": "forge",
            "topic": "Fallback participants debate",
            "participants": [],
        },
    )
    assert created.status_code == 200
    debate = created.json()["debate"]
    assert len(debate["participants"]) == 2
    assert debate["participants"][0]["provider"] == "openai"
    assert debate["participants"][1]["provider"] == "xai"


def test_debate_max_rounds_bounds(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    invalid = client.post(
        "/workspace/debates",
        json={
            "project_id": "forge",
            "topic": "Bounds check debate",
            "max_rounds": 0,
        },
    )
    assert invalid.status_code == 422


def test_get_debate_not_found_returns_404(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    fetched = client.get("/workspace/debates/deb_missing")
    assert fetched.status_code == 404


def test_list_debates_limit_validation(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    listed = client.get("/workspace/debates", params={"project_id": "forge", "limit": 0})
    assert listed.status_code == 422


def test_debate_runtime_validation_error_is_422(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))

    def fail_start_debate(self, **kwargs):
        raise ValueError("participants.provider must be one of: openai, xai")

    monkeypatch.setattr(DebateService, "start_debate", fail_start_debate)
    app = build_app()
    client = TestClient(app)

    created = client.post(
        "/workspace/debates",
        json={
            "project_id": "forge",
            "topic": "Runtime validation path",
            "participants": [{"provider": "openai", "model": "test-model"}],
        },
    )
    assert created.status_code == 422
    assert "participants.provider" in str(created.json().get("detail"))


def test_execution_create_approve_and_fetch(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    created = client.post(
        "/workspace/executions",
        json={
            "project_id": "forge",
            "plan": "Inspect current runtime.\nAdd executor endpoints.\nRun targeted tests.",
        },
    )
    assert created.status_code == 200
    payload = created.json()
    execution_id = payload["execution"]["execution_id"]
    assert payload["execution"]["status"] == "pending_approval"

    approved = client.post(
        f"/workspace/executions/{execution_id}/approval",
        json={"approved": True, "note": "record-only"},
    )
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["execution"]["status"] == "completed"
    assert approved_payload["execution"]["execution"]["applied"] is False

    fetched = client.get(f"/workspace/executions/{execution_id}")
    assert fetched.status_code == 200
    assert fetched.json()["execution"]["execution_id"] == execution_id


def test_execution_create_change_plan_mode(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    created = client.post(
        "/workspace/executions",
        json={
            "project_id": "forge",
            "plan": "Update the UI.\nAdd a change plan mode.",
            "execution_mode": "change_plan_v1",
        },
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["execution"]["proposal"]["mode"] == "change_plan_v1"
    assert payload["execution"]["proposal"]["patch_plan"]["format"] == "manual_patch_outline_v1"
    assert "workspace_ai/ui/index.html" in payload["execution"]["proposal"]["patch_plan"]["targets"]
    assert "workspace_ai/workspace_runtime/executor_service.py" in payload["execution"]["proposal"]["patch_plan"]["targets"]
    assert "*** Update File: workspace_ai/ui/index.html" in payload["execution"]["proposal"]["patch_draft"]

    execution_id = payload["execution"]["execution_id"]
    approved = client.post(
        f"/workspace/executions/{execution_id}/approval",
        json={"approved": True, "note": "plan only"},
    )
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["execution"]["execution"]["mode"] == "change_plan_v1"
    assert approved_payload["execution"]["execution"]["applied"] is False
    assert any("tests/integration/test_sessions_api.py" in command for command in approved_payload["execution"]["execution"]["commands"])
    assert "*** Update File: workspace_ai/ui/index.html" in approved_payload["execution"]["execution"]["patch_draft"]


def test_execution_created_from_debate_includes_artifacts(monkeypatch, isolated_workspace_env, tmp_path: Path):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    artifact_path = tmp_path / "exec_context.txt"
    artifact_path.write_text("Execution should carry artifact context from the debate.", encoding="utf-8")
    app = build_app()
    client = TestClient(app)

    debate_created = client.post(
        "/workspace/debates",
        json={
            "project_id": "forge",
            "topic": "Execution context inheritance",
            "files": [str(artifact_path)],
            "participants": [{"provider": "openai", "model": "test-model"}],
            "max_rounds": 1,
        },
    )
    assert debate_created.status_code == 200
    debate_id = debate_created.json()["debate"]["debate_id"]

    execution_created = client.post(
        "/workspace/executions",
        json={"project_id": "forge", "debate_id": debate_id, "plan": ""},
    )
    assert execution_created.status_code == 200
    execution = execution_created.json()["execution"]
    assert execution["source_plan"]["artifacts"][0]["label"] == "exec_context.txt"
    assert execution["proposal"]["source"]["artifacts"][0]["kind"] == "text"
    assert "exec_context.txt" in execution["proposal"]["artifact_summary"]


def test_execution_create_from_missing_debate_is_422(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    created = client.post(
        "/workspace/executions",
        json={"project_id": "forge", "debate_id": "deb_missing", "plan": ""},
    )
    assert created.status_code == 422


def test_execution_invalid_mode_is_422(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    created = client.post(
        "/workspace/executions",
        json={"project_id": "forge", "plan": "Review proposal.", "execution_mode": "bad_mode"},
    )
    assert created.status_code == 422


def test_execution_second_approval_returns_409(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    created = client.post(
        "/workspace/executions",
        json={"project_id": "forge", "plan": "Review proposal."},
    )
    execution_id = created.json()["execution"]["execution_id"]

    first = client.post(
        f"/workspace/executions/{execution_id}/approval",
        json={"approved": False, "note": "not now"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/workspace/executions/{execution_id}/approval",
        json={"approved": True, "note": "retry"},
    )
    assert second.status_code == 409
