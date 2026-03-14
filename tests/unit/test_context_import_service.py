from __future__ import annotations

import pytest

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.context_import_service import ContextImportService


def test_create_and_list(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = ContextImportService(store=store)

    item = svc.create(project_id="proj1", source_label="Design doc", content="Use hexagonal architecture.", category="project_background")
    assert item["import_id"].startswith("ctximp_")
    assert item["project_id"] == "proj1"
    assert item["category"] == "project_background"
    assert item["enabled"] is True

    result = svc.list_imports(project_id="proj1")
    assert result["count"] == 1
    assert result["imports"][0]["source_label"] == "Design doc"


def test_list_filters_by_project(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = ContextImportService(store=store)

    svc.create(project_id="alpha", source_label="A", content="alpha content", category="reference")
    svc.create(project_id="beta", source_label="B", content="beta content", category="reference")

    alpha = svc.list_imports(project_id="alpha")
    assert alpha["count"] == 1
    assert alpha["imports"][0]["project_id"] == "alpha"


def test_set_enabled_toggle(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = ContextImportService(store=store)

    item = svc.create(project_id="proj1", source_label="Note", content="content", category="transient")
    import_id = item["import_id"]

    disabled = svc.set_enabled(import_id=import_id, enabled=False)
    assert disabled["status"] == "ok"
    assert disabled["import"]["enabled"] is False

    re_enabled = svc.set_enabled(import_id=import_id, enabled=True)
    assert re_enabled["import"]["enabled"] is True


def test_set_enabled_not_found(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = ContextImportService(store=store)
    result = svc.set_enabled(import_id="ctximp_nonexistent", enabled=False)
    assert result["status"] == "not_found"


def test_delete(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = ContextImportService(store=store)

    item = svc.create(project_id="proj1", source_label="Del me", content="ephemeral", category="transient")
    result = svc.delete(import_id=item["import_id"])
    assert result["status"] == "ok"

    listed = svc.list_imports(project_id="proj1")
    assert listed["count"] == 0


def test_delete_not_found(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = ContextImportService(store=store)
    result = svc.delete(import_id="ctximp_missing")
    assert result["status"] == "not_found"


def test_build_context_block_only_enabled(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = ContextImportService(store=store)

    svc.create(project_id="proj1", source_label="Active", content="This should appear.", category="reference")
    item2 = svc.create(project_id="proj1", source_label="Inactive", content="This should NOT appear.", category="transient")
    svc.set_enabled(import_id=item2["import_id"], enabled=False)

    block = svc.build_context_block(project_id="proj1")
    assert "This should appear." in block
    assert "This should NOT appear." not in block
    assert "Imported context:" in block
    assert "Reference" in block
    assert "Active" in block


def test_build_context_block_empty(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = ContextImportService(store=store)
    block = svc.build_context_block(project_id="empty_project")
    assert block == ""


def test_invalid_category_raises(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    with pytest.raises(ValueError, match="category"):
        store.create_context_import(
            project_id="proj1", source_label="bad", content="x", category="unknown_cat"
        )
