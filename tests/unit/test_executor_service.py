from __future__ import annotations

from pathlib import Path

import pytest

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.executor_service import ExecutorService


def _executor_service(isolated_workspace_env) -> ExecutorService:
    store = SessionStore(db_path=str(isolated_workspace_env))
    return ExecutorService(store=store)


def test_executor_service_requires_plan_source(isolated_workspace_env):
    service = _executor_service(isolated_workspace_env)
    with pytest.raises(ValueError, match="debate_id or plan"):
        service.create_execution(project_id="forge")


def test_executor_service_creates_from_manual_plan(isolated_workspace_env):
    service = _executor_service(isolated_workspace_env)

    result = service.create_execution(
        project_id="forge",
        plan="Inspect the router.\nAdd execution endpoints.\nVerify test coverage.",
    )
    execution = result["execution"]
    assert result["status"] == "ok"
    assert execution["status"] == "pending_approval"
    assert execution["proposal"]["requires_approval"] is True
    assert len(execution["proposal"]["steps"]) == 3


def test_executor_service_creates_change_plan_mode(isolated_workspace_env):
    service = _executor_service(isolated_workspace_env)

    result = service.create_execution(
        project_id="forge",
        plan="Update the debate panel UI.\nAdd a safer execution mode in the executor.\nRun the API tests.",
        execution_mode="change_plan_v1",
    )
    execution = result["execution"]

    assert execution["proposal"]["mode"] == "change_plan_v1"
    assert execution["proposal"]["action_type"] == "change_plan"
    assert "tests/integration/test_sessions_api.py" in execution["proposal"]["commands"][0] or "tests/integration/test_sessions_api.py" in " ".join(execution["proposal"]["commands"])
    assert "tests/unit/test_executor_service.py" in " ".join(execution["proposal"]["commands"])
    assert execution["proposal"]["patch_plan"]["format"] == "manual_patch_outline_v1"
    assert "workspace_ai/ui/index.html" in execution["proposal"]["patch_plan"]["targets"]
    assert "workspace_ai/workspace_runtime/executor_service.py" in execution["proposal"]["patch_plan"]["targets"]
    assert "*** Update File: workspace_ai/ui/index.html" in execution["proposal"]["patch_draft"]


def test_executor_service_can_create_from_debate_and_approve(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    debate = store.create_debate(
        project_id="forge",
        topic="Executor rollout",
        bottlenecks="Need safe execution",
        files=[],
        participants=[{"provider": "openai", "model": "test-model"}],
        max_rounds=2,
        judge_provider="openai",
    )
    store.finalize_debate(
        debate_id=debate["debate_id"],
        final_plan={"content": "Review the backend.\nPrepare approval gate."},
        status="completed",
    )
    service = ExecutorService(store=store)

    created = service.create_execution(project_id="forge", debate_id=debate["debate_id"])
    execution_id = created["execution"]["execution_id"]

    approved = service.decide_execution(execution_id=execution_id, approved=True, note="safe to record")
    assert approved["status"] == "ok"
    assert approved["execution"]["status"] == "completed"
    assert approved["execution"]["execution"]["applied"] is False
    assert len(approved["execution"]["execution"]["steps"]) == 2


def test_executor_service_carries_debate_artifacts_into_proposal(isolated_workspace_env, tmp_path: Path):
    store = SessionStore(db_path=str(isolated_workspace_env))
    artifact_path = tmp_path / "executor_notes.txt"
    artifact_path.write_text("Execution should preserve debate artifact context.", encoding="utf-8")
    debate = store.create_debate(
        project_id="forge",
        topic="Executor artifact grounding",
        bottlenecks="Need the same context in execution",
        files=[
            {
                "path": str(artifact_path),
                "label": "executor_notes.txt",
                "exists": True,
                "kind": "text",
                "size_bytes": artifact_path.stat().st_size,
                "preview": "Execution should preserve debate artifact context.",
            }
        ],
        participants=[{"provider": "openai", "model": "test-model"}],
        max_rounds=2,
        judge_provider="openai",
    )
    store.finalize_debate(
        debate_id=debate["debate_id"],
        final_plan={"content": "Review artifact-backed plan.\nRecord execution proposal."},
        status="completed",
    )
    service = ExecutorService(store=store)

    created = service.create_execution(project_id="forge", debate_id=debate["debate_id"])
    execution = created["execution"]

    assert execution["source_plan"]["artifacts"][0]["label"] == "executor_notes.txt"
    assert execution["proposal"]["source"]["artifacts"][0]["kind"] == "text"
    assert "executor_notes.txt" in execution["proposal"]["artifact_summary"]
    assert "preserve debate artifact context" in execution["proposal"]["artifact_summary"]


def test_executor_service_prefers_artifact_targets_for_change_plan(isolated_workspace_env, tmp_path: Path):
    store = SessionStore(db_path=str(isolated_workspace_env))
    artifact_path = tmp_path / "workspace_api" / "router.py"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("def route():\n    return 'ok'\n", encoding="utf-8")
    debate = store.create_debate(
        project_id="forge",
        topic="Router-targeted change plan",
        bottlenecks="Need a repo-aware patch outline",
        files=[
            {
                "path": "workspace_ai/workspace_api/router.py",
                "label": "router.py",
                "exists": True,
                "kind": "text",
                "size_bytes": artifact_path.stat().st_size,
                "preview": "def route(): return 'ok'",
            }
        ],
        participants=[{"provider": "openai", "model": "test-model"}],
        max_rounds=1,
        judge_provider="openai",
    )
    store.finalize_debate(
        debate_id=debate["debate_id"],
        final_plan={"content": "Update the router endpoint.\nAdd request validation.\nRun API tests."},
        status="completed",
    )
    service = ExecutorService(store=store)

    created = service.create_execution(
        project_id="forge",
        debate_id=debate["debate_id"],
        execution_mode="change_plan_v1",
    )
    proposal = created["execution"]["proposal"]

    assert proposal["patch_plan"]["targets"][0] == "workspace_ai/workspace_api/router.py"
    assert "Plan mentions API or routing changes." in " ".join(hunk["reason"] for hunk in proposal["patch_plan"]["hunks"])
    assert any("tests/integration/test_sessions_api.py" in command for command in proposal["commands"])
    assert "*** Update File: workspace_ai/workspace_api/router.py" in proposal["patch_draft"]


def test_executor_service_rejects_second_decision(isolated_workspace_env):
    service = _executor_service(isolated_workspace_env)
    created = service.create_execution(project_id="forge", plan="Inspect the store.")
    execution_id = created["execution"]["execution_id"]

    service.decide_execution(execution_id=execution_id, approved=False, note="stop")
    with pytest.raises(ValueError, match="not pending approval"):
        service.decide_execution(execution_id=execution_id, approved=True, note="retry")


def test_executor_service_rejects_unknown_mode(isolated_workspace_env):
    service = _executor_service(isolated_workspace_env)
    with pytest.raises(ValueError, match="execution_mode"):
        service.create_execution(project_id="forge", plan="Inspect the store.", execution_mode="bad_mode")


def test_executor_service_inherits_debate_context_import_ids(isolated_workspace_env):
    """When context_import_ids is not provided, execution inherits from the debate record."""
    store = SessionStore(db_path=str(isolated_workspace_env))
    imp = store.create_context_import(project_id="forge", source_label="Guide", content="Important context.", category="reference")
    debate = store.create_debate(
        project_id="forge",
        topic="Context inheritance test",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=1,
        judge_provider="openai",
        context_import_ids=[imp["import_id"]],
    )
    store.finalize_debate(debate_id=debate["debate_id"], final_plan={"content": "Run the suite."}, status="completed")
    service = ExecutorService(store=store)

    # No context_import_ids passed — backend should inherit from debate
    result = service.create_execution(project_id="forge", debate_id=debate["debate_id"])
    execution = result["execution"]

    assert result["status"] == "ok"
    assert imp["import_id"] in execution["context_import_ids"]
    assert execution["proposal"]["context_source"] == "inherited"


def test_executor_service_context_override_supersedes_debate(isolated_workspace_env):
    """Explicit context_import_ids override the debate's stored context_import_ids."""
    store = SessionStore(db_path=str(isolated_workspace_env))
    imp_a = store.create_context_import(project_id="forge", source_label="A", content="Context A.", category="reference")
    imp_b = store.create_context_import(project_id="forge", source_label="B", content="Context B.", category="reference")
    debate = store.create_debate(
        project_id="forge",
        topic="Override test",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=1,
        judge_provider="openai",
        context_import_ids=[imp_a["import_id"]],
    )
    store.finalize_debate(debate_id=debate["debate_id"], final_plan={"content": "Run checks."}, status="completed")
    service = ExecutorService(store=store)

    # Explicitly pass imp_b only — override the debate's imp_a selection
    result = service.create_execution(
        project_id="forge",
        debate_id=debate["debate_id"],
        context_import_ids=[imp_b["import_id"]],
    )
    execution = result["execution"]

    assert execution["context_import_ids"] == [imp_b["import_id"]]
    assert imp_a["import_id"] not in execution["context_import_ids"]
    assert execution["proposal"]["context_source"] == "override"


def test_executor_service_debate_with_no_context_import_ids_is_inherited_empty(isolated_workspace_env):
    """Debate with no context_import_ids → inherited source, empty resolved IDs (falls back to all enabled)."""
    store = SessionStore(db_path=str(isolated_workspace_env))
    debate = store.create_debate(
        project_id="forge",
        topic="No context debate",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=1,
        judge_provider="openai",
    )
    store.finalize_debate(debate_id=debate["debate_id"], final_plan={"content": "Plan here."}, status="completed")
    service = ExecutorService(store=store)

    result = service.create_execution(project_id="forge", debate_id=debate["debate_id"])
    execution = result["execution"]

    assert execution["proposal"]["context_source"] == "inherited"
    assert execution["context_import_ids"] == []


def test_executor_service_manual_plan_context_source_is_manual(isolated_workspace_env):
    """Execution from a standalone plan (no debate_id) → context_source = 'manual'."""
    service = _executor_service(isolated_workspace_env)
    result = service.create_execution(project_id="forge", plan="Review the architecture.")
    execution = result["execution"]
    assert execution["proposal"]["context_source"] == "manual"
