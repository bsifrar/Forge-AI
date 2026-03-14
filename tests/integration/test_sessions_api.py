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
    assert "anthropic" in payload["available_providers"]
    assert "provider_keys_configured" in payload
    assert "model_roles" in payload
    roles = payload["model_roles"]
    assert set(roles.keys()) == {"chat", "debate_a", "debate_b", "judge"}
    assert all("provider" in r and "model" in r for r in roles.values())


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
        raise ValueError("participants.provider must be one of: openai, xai, anthropic")

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


def test_context_imports_crud(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    # create
    created = client.post("/workspace/context-imports", json={
        "project_id": "forge",
        "source_label": "Design notes",
        "content": "Prefer async everywhere.",
        "category": "preference",
    })
    assert created.status_code == 200
    item = created.json()["import"]
    import_id = item["import_id"]
    assert item["enabled"] is True
    assert item["category"] == "preference"

    # list
    listed = client.get("/workspace/context-imports", params={"project_id": "forge"})
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["imports"][0]["import_id"] == import_id

    # disable
    toggled = client.post(f"/workspace/context-imports/{import_id}/enabled", json={"enabled": False})
    assert toggled.status_code == 200
    assert toggled.json()["import"]["enabled"] is False

    # re-enable
    toggled2 = client.post(f"/workspace/context-imports/{import_id}/enabled", json={"enabled": True})
    assert toggled2.status_code == 200
    assert toggled2.json()["import"]["enabled"] is True

    # delete
    deleted = client.delete(f"/workspace/context-imports/{import_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "ok"

    listed2 = client.get("/workspace/context-imports", params={"project_id": "forge"})
    assert listed2.json()["count"] == 0


def test_context_imports_invalid_category_is_422(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    resp = client.post("/workspace/context-imports", json={
        "project_id": "forge",
        "content": "some content",
        "category": "invalid_cat",
    })
    assert resp.status_code == 422


def test_context_import_enabled_not_found_is_404(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    resp = client.post("/workspace/context-imports/ctximp_missing/enabled", json={"enabled": False})
    assert resp.status_code == 404


def test_context_preview_includes_import_count(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    client.post("/workspace/context-imports", json={
        "project_id": "workspace",
        "source_label": "Arch notes",
        "content": "Monorepo. No ORM.",
        "category": "project_background",
    })
    preview = client.get("/workspace/context/preview", params={"project_id": "workspace"})
    assert preview.status_code == 200
    data = preview.json()
    assert data["imported_context_count"] == 1
    assert "Monorepo. No ORM." in data["system_prompt"]


def test_debate_stores_context_import_ids_override(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    # create two imports
    r1 = client.post("/workspace/context-imports", json={
        "project_id": "forge", "source_label": "Doc A", "content": "Doc A content.", "category": "reference",
    })
    r2 = client.post("/workspace/context-imports", json={
        "project_id": "forge", "source_label": "Doc B", "content": "Doc B content.", "category": "reference",
    })
    id1 = r1.json()["import"]["import_id"]
    id2 = r2.json()["import"]["import_id"]

    # start debate with override selecting only id1
    debate_resp = client.post("/workspace/debates", json={
        "project_id": "forge",
        "topic": "Context pack override test",
        "participants": [{"provider": "openai", "model": "test-model"}],
        "context_import_ids": [id1],
    })
    assert debate_resp.status_code == 200
    debate = debate_resp.json()["debate"]
    assert debate["context_import_ids"] == [id1]


def test_debate_context_import_ids_invalid_raises_422(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    debate_resp = client.post("/workspace/debates", json={
        "project_id": "forge",
        "topic": "Bad import id test",
        "participants": [{"provider": "openai", "model": "test-model"}],
        "context_import_ids": ["ctximp_doesnotexist"],
    })
    assert debate_resp.status_code == 422


def test_execution_inherits_context_import_ids_from_debate(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    r1 = client.post("/workspace/context-imports", json={
        "project_id": "forge", "source_label": "Spec", "content": "Use hexagonal arch.", "category": "project_background",
    })
    import_id = r1.json()["import"]["import_id"]

    debate_resp = client.post("/workspace/debates", json={
        "project_id": "forge",
        "topic": "Execution context pack test",
        "participants": [{"provider": "openai", "model": "test-model"}],
        "context_import_ids": [import_id],
    })
    debate_id = debate_resp.json()["debate"]["debate_id"]

    exec_resp = client.post("/workspace/executions", json={
        "project_id": "forge",
        "debate_id": debate_id,
        "execution_mode": "read_only_v1",
        "context_import_ids": [import_id],
    })
    assert exec_resp.status_code == 200
    execution = exec_resp.json()["execution"]
    assert execution["context_import_ids"] == [import_id]
    assert "Use hexagonal arch." in execution["proposal"].get("imported_context", "")


def test_context_preview_override_import_ids(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    r1 = client.post("/workspace/context-imports", json={
        "project_id": "workspace", "source_label": "Selected", "content": "selected content only.", "category": "reference",
    })
    r2 = client.post("/workspace/context-imports", json={
        "project_id": "workspace", "source_label": "Excluded", "content": "excluded content.", "category": "reference",
    })
    id1 = r1.json()["import"]["import_id"]

    preview = client.get("/workspace/context/preview", params={"project_id": "workspace", "import_ids": id1})
    assert preview.status_code == 200
    data = preview.json()
    assert "selected content only." in data["system_prompt"]
    assert "excluded content." not in data["system_prompt"]
    assert data["active_import_ids"] == [id1]


def test_handoff_missing_params_is_422(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    resp = client.get("/workspace/handoff")
    assert resp.status_code == 422


def test_handoff_debate_not_found_is_404(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    resp = client.get("/workspace/handoff", params={"debate_id": "deb_missing"})
    assert resp.status_code == 404


def test_handoff_execution_not_found_is_404(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    resp = client.get("/workspace/handoff", params={"execution_id": "exe_missing"})
    assert resp.status_code == 404


def test_handoff_from_debate(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    debate_resp = client.post("/workspace/debates", json={
        "project_id": "forge",
        "topic": "Handoff debate topic",
        "participants": [{"provider": "openai", "model": "test-model"}],
        "max_rounds": 1,
    })
    assert debate_resp.status_code == 200
    debate_id = debate_resp.json()["debate"]["debate_id"]

    resp = client.get("/workspace/handoff", params={"debate_id": debate_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    h = data["handoff"]
    assert h["debate_id"] == debate_id
    assert h["execution_id"] is None
    assert h["topic"] == "Handoff debate topic"
    assert "FORGE HANDOFF PACKAGE" in h["text"]
    assert "Handoff debate topic" in h["text"]
    assert "RECOMMENDED NEXT ACTION" in h["text"]


def test_handoff_from_execution(monkeypatch, isolated_workspace_env):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    app = build_app()
    client = TestClient(app)

    debate_resp = client.post("/workspace/debates", json={
        "project_id": "forge",
        "topic": "Handoff execution topic",
        "participants": [{"provider": "openai", "model": "test-model"}],
        "max_rounds": 1,
    })
    debate_id = debate_resp.json()["debate"]["debate_id"]

    exec_resp = client.post("/workspace/executions", json={
        "project_id": "forge",
        "debate_id": debate_id,
        "plan": "Execute the plan.",
        "execution_mode": "read_only_v1",
    })
    assert exec_resp.status_code == 200
    execution_id = exec_resp.json()["execution"]["execution_id"]

    resp = client.get("/workspace/handoff", params={"execution_id": execution_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    h = data["handoff"]
    assert h["execution_id"] == execution_id
    assert h["execution_mode"] == "read_only_v1"
    assert "FORGE HANDOFF PACKAGE" in h["text"]
    assert "RECOMMENDED NEXT ACTION" in h["text"]
