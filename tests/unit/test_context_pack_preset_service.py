from __future__ import annotations

import pytest

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.context_pack_preset_service import ContextPackPresetService


def _setup(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    service = ContextPackPresetService(store=store)
    imp = store.create_context_import(project_id="proj1", source_label="Guide", content="ctx", category="reference")
    return store, service, imp


def test_create_preset_and_list(isolated_workspace_env):
    store, service, imp = _setup(isolated_workspace_env)
    result = service.create(project_id="proj1", name="Core", import_ids=[imp["import_id"]])
    assert result["status"] == "ok"
    preset = result["preset"]
    assert preset["name"] == "Core"
    assert preset["project_id"] == "proj1"
    assert imp["import_id"] in preset["import_ids"]

    listed = service.list_presets(project_id="proj1")
    assert listed["count"] == 1
    assert listed["presets"][0]["preset_id"] == preset["preset_id"]


def test_create_preset_filters_missing_import_ids(isolated_workspace_env):
    store, service, imp = _setup(isolated_workspace_env)
    # Pass a bogus ID alongside a real one; only real one should be stored
    result = service.create(project_id="proj1", name="Partial", import_ids=[imp["import_id"], "ctximp_doesnotexist"])
    assert result["status"] == "ok"
    assert result["preset"]["import_ids"] == [imp["import_id"]]


def test_create_preset_filters_wrong_project_ids(isolated_workspace_env):
    store, service, imp = _setup(isolated_workspace_env)
    # imp belongs to proj1, but we create a preset for proj2 — should be filtered out
    result = service.create(project_id="proj2", name="Empty", import_ids=[imp["import_id"]])
    assert result["status"] == "ok"
    assert result["preset"]["import_ids"] == []


def test_create_preset_requires_name(isolated_workspace_env):
    _, service, _ = _setup(isolated_workspace_env)
    with pytest.raises(ValueError, match="name is required"):
        service.create(project_id="proj1", name="  ", import_ids=[])


def test_create_preset_allows_empty_import_ids(isolated_workspace_env):
    _, service, _ = _setup(isolated_workspace_env)
    result = service.create(project_id="proj1", name="Empty preset", import_ids=[])
    assert result["status"] == "ok"
    assert result["preset"]["import_ids"] == []


def test_apply_preset_returns_valid_ids(isolated_workspace_env):
    store, service, imp = _setup(isolated_workspace_env)
    preset = service.create(project_id="proj1", name="Full", import_ids=[imp["import_id"]])["preset"]
    applied = service.apply(preset_id=preset["preset_id"], project_id="proj1")
    assert applied["status"] == "ok"
    assert applied["import_ids"] == [imp["import_id"]]
    assert applied["filtered_count"] == 0


def test_apply_preset_filters_deleted_imports(isolated_workspace_env):
    store, service, imp = _setup(isolated_workspace_env)
    imp2 = store.create_context_import(project_id="proj1", source_label="Extra", content="extra", category="reference")
    preset = service.create(project_id="proj1", name="Two", import_ids=[imp["import_id"], imp2["import_id"]])["preset"]

    # Delete imp2 — apply should silently filter it out
    store.delete_context_import(import_id=imp2["import_id"])
    applied = service.apply(preset_id=preset["preset_id"], project_id="proj1")
    assert applied["status"] == "ok"
    assert applied["import_ids"] == [imp["import_id"]]
    assert applied["filtered_count"] == 1


def test_apply_missing_preset_returns_not_found(isolated_workspace_env):
    _, service, _ = _setup(isolated_workspace_env)
    result = service.apply(preset_id="cxpre_doesnotexist", project_id="proj1")
    assert result["status"] == "not_found"


def test_update_preset_name(isolated_workspace_env):
    store, service, imp = _setup(isolated_workspace_env)
    preset = service.create(project_id="proj1", name="Old", import_ids=[imp["import_id"]])["preset"]
    updated = service.update(preset_id=preset["preset_id"], name="New Name")
    assert updated["status"] == "ok"
    assert updated["preset"]["name"] == "New Name"
    assert updated["preset"]["import_ids"] == [imp["import_id"]]  # unchanged


def test_update_preset_import_ids(isolated_workspace_env):
    store, service, imp = _setup(isolated_workspace_env)
    imp2 = store.create_context_import(project_id="proj1", source_label="B", content="b", category="reference")
    preset = service.create(project_id="proj1", name="One", import_ids=[imp["import_id"]])["preset"]
    updated = service.update(preset_id=preset["preset_id"], import_ids=[imp2["import_id"]])
    assert updated["status"] == "ok"
    assert updated["preset"]["import_ids"] == [imp2["import_id"]]


def test_update_preset_not_found(isolated_workspace_env):
    _, service, _ = _setup(isolated_workspace_env)
    result = service.update(preset_id="cxpre_ghost", name="X")
    assert result["status"] == "not_found"


def test_delete_preset(isolated_workspace_env):
    _, service, imp = _setup(isolated_workspace_env)
    preset = service.create(project_id="proj1", name="ToDelete", import_ids=[imp["import_id"]])["preset"]
    result = service.delete(preset_id=preset["preset_id"])
    assert result["status"] == "ok"
    assert service.list_presets(project_id="proj1")["count"] == 0


def test_delete_missing_preset_returns_not_found(isolated_workspace_env):
    _, service, _ = _setup(isolated_workspace_env)
    result = service.delete(preset_id="cxpre_ghost")
    assert result["status"] == "not_found"


def test_list_presets_scoped_by_project(isolated_workspace_env):
    store, service, imp = _setup(isolated_workspace_env)
    imp2 = store.create_context_import(project_id="proj2", source_label="P2", content="ctx2", category="reference")
    service.create(project_id="proj1", name="P1 preset", import_ids=[imp["import_id"]])
    service.create(project_id="proj2", name="P2 preset", import_ids=[imp2["import_id"]])

    proj1_presets = service.list_presets(project_id="proj1")
    assert proj1_presets["count"] == 1
    assert proj1_presets["presets"][0]["name"] == "P1 preset"

    all_presets = service.list_presets()
    assert all_presets["count"] == 2


def test_older_executions_without_presets_unaffected(isolated_workspace_env):
    """Confirm that the preset table presence doesn't break existing execution/debate flow."""
    store = SessionStore(db_path=str(isolated_workspace_env))
    # Just verify the store initializes cleanly and existing ops still work
    debate = store.create_debate(
        project_id="proj1", topic="T", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai"
    )
    assert debate["debate_id"].startswith("deb_")
    assert store.list_context_pack_presets(project_id="proj1") == []
