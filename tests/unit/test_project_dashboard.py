from __future__ import annotations

import pytest

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.executor_service import ExecutorService


def _store(isolated_workspace_env) -> SessionStore:
    return SessionStore(db_path=str(isolated_workspace_env))


def test_dashboard_empty_project_returns_zero_counts(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    result = store.get_project_dashboard(project_id="empty_proj")
    assert result["project_id"] == "empty_proj"
    assert result["debate_summary"]["total"] == 0
    assert result["execution_summary"]["total"] == 0
    assert result["recent_debates"] == []
    assert result["recent_executions"] == []


def test_dashboard_debate_counts_by_status(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    d1 = store.create_debate(project_id="proj", topic="A", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")
    d2 = store.create_debate(project_id="proj", topic="B", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")
    d3 = store.create_debate(project_id="proj", topic="C", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")
    store.finalize_debate(debate_id=d1["debate_id"], final_plan={"content": "plan"}, status="completed")
    store.finalize_debate(debate_id=d2["debate_id"], final_plan={"content": "plan"}, status="max_rounds")
    # d3 stays "pending"

    result = store.get_project_dashboard(project_id="proj")
    ds = result["debate_summary"]
    assert ds["total"] == 3
    assert ds["completed"] == 1
    assert ds["max_rounds"] == 1
    assert ds["pending"] == 1
    assert ds["failed"] == 0


def test_dashboard_execution_counts_by_status(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    executor = ExecutorService(store=store)
    e1 = executor.create_execution(project_id="proj", plan="Step A.")
    e2 = executor.create_execution(project_id="proj", plan="Step B.")
    e3 = executor.create_execution(project_id="proj", plan="Step C.")
    # approve e1, reject e2, leave e3 pending
    executor.decide_execution(execution_id=e1["execution"]["execution_id"], approved=True, note="ok")
    executor.decide_execution(execution_id=e2["execution"]["execution_id"], approved=False, note="no")

    result = store.get_project_dashboard(project_id="proj")
    es = result["execution_summary"]
    assert es["total"] == 3
    assert es["completed"] == 1
    assert es["rejected"] == 1
    assert es["pending_approval"] == 1


def test_dashboard_project_scoping_excludes_other_projects(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    store.create_debate(project_id="proj_a", topic="A-debate", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")
    store.create_debate(project_id="proj_b", topic="B-debate", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")

    result_a = store.get_project_dashboard(project_id="proj_a")
    result_b = store.get_project_dashboard(project_id="proj_b")

    assert result_a["debate_summary"]["total"] == 1
    assert result_b["debate_summary"]["total"] == 1
    assert result_a["recent_debates"][0]["topic"] == "A-debate"
    assert result_b["recent_debates"][0]["topic"] == "B-debate"


def test_dashboard_recent_debates_ordered_by_updated_at(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    d1 = store.create_debate(project_id="proj", topic="Older", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")
    d2 = store.create_debate(project_id="proj", topic="Newer", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")
    # Finalize d1 later to bump its updated_at
    store.finalize_debate(debate_id=d1["debate_id"], final_plan={"content": "plan"}, status="completed")

    result = store.get_project_dashboard(project_id="proj")
    topics = [d["topic"] for d in result["recent_debates"]]
    # d1 was finalized last → updated_at most recent
    assert topics[0] == "Older"


def test_dashboard_recent_executions_include_mode_and_topic(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    debate = store.create_debate(project_id="proj", topic="Mode test debate", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")
    store.finalize_debate(debate_id=debate["debate_id"], final_plan={"content": "Do the thing."}, status="completed")
    executor = ExecutorService(store=store)
    executor.create_execution(project_id="proj", debate_id=debate["debate_id"], execution_mode="change_plan_v1")

    result = store.get_project_dashboard(project_id="proj")
    execs = result["recent_executions"]
    assert len(execs) == 1
    assert execs[0]["mode"] == "change_plan_v1"
    assert execs[0]["topic"] == "Mode test debate"


def test_dashboard_recent_limit_is_respected(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    for i in range(8):
        store.create_debate(project_id="proj", topic=f"D{i}", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")

    result = store.get_project_dashboard(project_id="proj", recent_limit=3)
    assert len(result["recent_debates"]) == 3


def test_dashboard_recent_debate_fields_are_present(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    store.create_debate(project_id="proj", topic="Field check", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")

    result = store.get_project_dashboard(project_id="proj")
    d = result["recent_debates"][0]
    for field in ["debate_id", "topic", "status", "debate_style", "updated_at", "created_at"]:
        assert field in d


def test_dashboard_recent_execution_fields_are_present(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    executor = ExecutorService(store=store)
    executor.create_execution(project_id="proj", plan="Check fields.")

    result = store.get_project_dashboard(project_id="proj")
    e = result["recent_executions"][0]
    for field in ["execution_id", "debate_id", "status", "mode", "topic", "source_type", "updated_at", "created_at"]:
        assert field in e


def test_dashboard_handoff_source_type_is_surfaced(isolated_workspace_env):
    store = _store(isolated_workspace_env)
    debate = store.create_debate(project_id="proj", topic="Handoff dash", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai")
    store.finalize_debate(debate_id=debate["debate_id"], final_plan={"content": "plan"}, status="completed")
    executor = ExecutorService(store=store)
    executor.create_execution_from_handoff(debate_id=debate["debate_id"])

    result = store.get_project_dashboard(project_id="proj")
    e = result["recent_executions"][0]
    assert e["source_type"] == "handoff_v1"


def test_dashboard_session_manager_raises_on_whitespace_project_id(isolated_workspace_env):
    from workspace_ai.workspace_runtime.session_manager import SessionManager
    from workspace_ai.adapters.null_adapter import NullAdapter
    store = _store(isolated_workspace_env)
    manager = SessionManager(adapter=NullAdapter(), store=store)
    with pytest.raises(ValueError, match="project_id is required"):
        manager.get_project_dashboard(project_id="   ")


def test_dashboard_session_manager_returns_status_ok(isolated_workspace_env, monkeypatch):
    monkeypatch.setenv("WORKSPACE_STORAGE_PATH", str(isolated_workspace_env))
    from workspace_ai.workspace_runtime.session_manager import SessionManager
    from workspace_ai.adapters.null_adapter import NullAdapter
    store = _store(isolated_workspace_env)
    from workspace_ai.workspace_runtime.settings_service import SettingsService
    from workspace_ai.workspace_runtime.session_manager import SessionManager
    manager = SessionManager(adapter=NullAdapter(), store=store)

    result = manager.get_project_dashboard(project_id="proj", recent_limit=3)
    assert result["status"] == "ok"
    assert result["project_id"] == "proj"


def test_dashboard_session_manager_raises_on_blank_project(isolated_workspace_env):
    from workspace_ai.workspace_runtime.session_manager import SessionManager
    from workspace_ai.adapters.null_adapter import NullAdapter
    store = _store(isolated_workspace_env)
    manager = SessionManager(adapter=NullAdapter(), store=store)

    with pytest.raises(ValueError, match="project_id is required"):
        manager.get_project_dashboard(project_id="")
