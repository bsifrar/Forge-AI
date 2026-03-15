from __future__ import annotations

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.execution_export_service import ExecutionExportService
from workspace_ai.workspace_runtime.executor_service import ExecutorService


def _setup(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    export_service = ExecutionExportService(store=store)
    executor = ExecutorService(store=store)
    return store, export_service, executor


def test_export_not_found_returns_not_found(isolated_workspace_env):
    _, export_service, _ = _setup(isolated_workspace_env)
    result = export_service.export_execution(execution_id="exe_ghost")
    assert result["status"] == "not_found"
    assert result["execution_id"] == "exe_ghost"


def test_export_read_only_execution_returns_ok(isolated_workspace_env):
    store, export_service, executor = _setup(isolated_workspace_env)
    created = executor.create_execution(project_id="forge", plan="Review the session store.\nVerify API coverage.")
    execution_id = created["execution"]["execution_id"]

    result = export_service.export_execution(execution_id=execution_id)
    assert result["status"] == "ok"
    assert result["execution_id"] == execution_id
    assert "text" in result["export"]
    assert result["export"]["char_count"] > 0
    assert result["export"]["line_count"] > 0


def test_export_text_contains_header_and_footer(isolated_workspace_env):
    _, export_service, executor = _setup(isolated_workspace_env)
    created = executor.create_execution(project_id="forge", plan="Inspect the router.")
    execution_id = created["execution"]["execution_id"]

    text = export_service.export_execution(execution_id=execution_id)["export"]["text"]
    assert "FORGE EXECUTION EXPORT" in text
    assert "END FORGE EXECUTION EXPORT" in text


def test_export_text_includes_plan_steps(isolated_workspace_env):
    _, export_service, executor = _setup(isolated_workspace_env)
    created = executor.create_execution(
        project_id="forge",
        plan="Inspect the router.\nAdd execution endpoints.\nVerify test coverage.",
    )
    execution_id = created["execution"]["execution_id"]

    text = export_service.export_execution(execution_id=execution_id)["export"]["text"]
    assert "PROPOSED STEPS" in text
    assert "Inspect the router." in text


def test_export_text_includes_metadata_fields(isolated_workspace_env):
    _, export_service, executor = _setup(isolated_workspace_env)
    created = executor.create_execution(project_id="forge", plan="Run diagnostics.")
    execution_id = created["execution"]["execution_id"]

    text = export_service.export_execution(execution_id=execution_id)["export"]["text"]
    assert "Execution ID" in text
    assert execution_id in text
    assert "Project" in text
    assert "forge" in text
    assert "Status" in text
    assert "Mode" in text


def test_export_change_plan_includes_commands_and_patch(isolated_workspace_env):
    _, export_service, executor = _setup(isolated_workspace_env)
    created = executor.create_execution(
        project_id="forge",
        plan="Update the debate panel UI.\nAdd a safer execution mode in the executor.\nRun the API tests.",
        execution_mode="change_plan_v1",
    )
    execution_id = created["execution"]["execution_id"]

    text = export_service.export_execution(execution_id=execution_id)["export"]["text"]
    assert "SUGGESTED COMMANDS" in text
    assert "PATCH PLAN" in text
    assert "PATCH DRAFT" in text


def test_export_includes_debate_source_when_linked(isolated_workspace_env):
    store, export_service, executor = _setup(isolated_workspace_env)
    debate = store.create_debate(
        project_id="forge",
        topic="Export-linked debate",
        bottlenecks="",
        files=[],
        participants=[{"provider": "openai", "model": "test-model"}],
        max_rounds=1,
        judge_provider="openai",
    )
    store.finalize_debate(
        debate_id=debate["debate_id"],
        final_plan={"content": "Migrate the session store.\nUpdate the router."},
        status="completed",
    )
    created = executor.create_execution(project_id="forge", debate_id=debate["debate_id"])
    execution_id = created["execution"]["execution_id"]

    text = export_service.export_execution(execution_id=execution_id)["export"]["text"]
    assert "Debate ID" in text
    assert debate["debate_id"] in text
    assert "Export-linked debate" in text
    assert "SOURCE PLAN" in text
    assert "Migrate the session store." in text


def test_export_handoff_source_type_is_included(isolated_workspace_env):
    store, export_service, executor = _setup(isolated_workspace_env)
    debate = store.create_debate(
        project_id="forge",
        topic="Handoff export topic",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=1,
        judge_provider="openai",
    )
    store.finalize_debate(
        debate_id=debate["debate_id"],
        final_plan={"content": "Deploy the service."},
        status="completed",
    )
    created = executor.create_execution_from_handoff(debate_id=debate["debate_id"])
    execution_id = created["execution"]["execution_id"]

    text = export_service.export_execution(execution_id=execution_id)["export"]["text"]
    assert "handoff_v1" in text


def test_export_context_source_is_shown(isolated_workspace_env):
    store, export_service, executor = _setup(isolated_workspace_env)
    imp = store.create_context_import(project_id="forge", source_label="Ref", content="ctx", category="reference")
    debate = store.create_debate(
        project_id="forge",
        topic="Context source export",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=1,
        judge_provider="openai",
        context_import_ids=[imp["import_id"]],
    )
    store.finalize_debate(debate_id=debate["debate_id"], final_plan={"content": "Apply context."}, status="completed")
    created = executor.create_execution(project_id="forge", debate_id=debate["debate_id"])
    execution_id = created["execution"]["execution_id"]

    text = export_service.export_execution(execution_id=execution_id)["export"]["text"]
    assert "inherited" in text
    assert "1 import" in text
