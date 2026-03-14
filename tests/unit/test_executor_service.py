from __future__ import annotations

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


def test_executor_service_rejects_second_decision(isolated_workspace_env):
    service = _executor_service(isolated_workspace_env)
    created = service.create_execution(project_id="forge", plan="Inspect the store.")
    execution_id = created["execution"]["execution_id"]

    service.decide_execution(execution_id=execution_id, approved=False, note="stop")
    with pytest.raises(ValueError, match="not pending approval"):
        service.decide_execution(execution_id=execution_id, approved=True, note="retry")
