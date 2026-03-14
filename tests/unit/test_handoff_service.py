from __future__ import annotations

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.handoff_service import HandoffService


def test_build_from_debate_not_found(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    result = svc.build_from_debate(debate_id="deb_missing")
    assert result["status"] == "not_found"
    assert result["debate_id"] == "deb_missing"


def test_build_from_execution_not_found(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    result = svc.build_from_execution(execution_id="exec_missing")
    assert result["status"] == "not_found"
    assert result["execution_id"] == "exec_missing"


def test_build_from_debate_basic(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)

    debate = store.create_debate(
        project_id="proj1",
        topic="Test topic",
        bottlenecks="",
        files=[],
        participants=[{"provider": "openai", "model": "gpt-4o"}],
        max_rounds=3,
        judge_provider="openai",
    )
    debate_id = debate["debate_id"]

    result = svc.build_from_debate(debate_id=debate_id)
    assert result["status"] == "ok"
    h = result["handoff"]
    assert h["debate_id"] == debate_id
    assert h["execution_id"] is None
    assert h["project_id"] == "proj1"
    assert h["topic"] == "Test topic"
    assert "text" in h
    assert "FORGE HANDOFF PACKAGE" in h["text"]
    assert "TOPIC" in h["text"]
    assert "Test topic" in h["text"]


def test_build_from_debate_text_has_next_action(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)

    debate = store.create_debate(
        project_id="proj1",
        topic="Plan something",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=2,
        judge_provider="openai",
    )
    result = svc.build_from_debate(debate_id=debate["debate_id"])
    h = result["handoff"]
    assert "RECOMMENDED NEXT ACTION" in h["text"]
    assert h["recommended_next_action"]


def test_build_from_debate_with_final_plan(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)

    debate = store.create_debate(
        project_id="proj1",
        topic="Architecture debate",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=1,
        judge_provider="openai",
    )
    debate_id = debate["debate_id"]
    # Simulate a completed debate by updating the record directly
    with store._connect() as conn:
        conn.execute(
            "UPDATE debates SET status='completed', final_plan_json=? WHERE debate_id=?",
            ('{"content": "Use event sourcing."}', debate_id),
        )
        conn.commit()

    result = svc.build_from_debate(debate_id=debate_id)
    h = result["handoff"]
    assert h["final_plan"] == "Use event sourcing."
    assert "Use event sourcing." in h["text"]
    assert "converged" in h["recommended_next_action"].lower()


def test_build_from_execution_basic(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)

    debate = store.create_debate(
        project_id="proj1",
        topic="Exec test topic",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=1,
        judge_provider="openai",
    )
    execution = store.create_execution(
        project_id="proj1",
        debate_id=debate["debate_id"],
        source_plan={"content": "Step 1: do X.", "topic": "Exec test topic", "artifacts": []},
        proposal={
            "mode": "read_only_v1",
            "commands": None,
            "patch_draft": None,
            "imported_context": "",
            "source": {"artifacts": []},
            "artifact_summary": "",
        },
    )
    execution_id = execution["execution_id"]

    result = svc.build_from_execution(execution_id=execution_id)
    assert result["status"] == "ok"
    h = result["handoff"]
    assert h["execution_id"] == execution_id
    assert h["debate_id"] == debate["debate_id"]
    assert h["final_plan"] == "Step 1: do X."
    assert h["execution_mode"] == "read_only_v1"
    assert "FORGE HANDOFF PACKAGE" in h["text"]
    assert "Step 1: do X." in h["text"]


def test_build_from_execution_with_commands_and_patch(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)

    execution = store.create_execution(
        project_id="proj1",
        debate_id="",
        source_plan={"content": "Plan text here.", "topic": "Patch test", "artifacts": []},
        proposal={
            "mode": "change_plan_v1",
            "commands": ["pytest tests/", "git diff"],
            "patch_draft": "--- a/foo.py\n+++ b/foo.py",
            "imported_context": "Some baked context.",
            "source": {"artifacts": []},
            "artifact_summary": "",
        },
    )
    result = svc.build_from_execution(execution_id=execution["execution_id"])
    h = result["handoff"]
    assert h["execution_mode"] == "change_plan_v1"
    assert h["suggested_commands"] == ["pytest tests/", "git diff"]
    assert h["patch_draft"] == "--- a/foo.py\n+++ b/foo.py"
    assert h["imported_context"] == "Some baked context."
    assert "SUGGESTED COMMANDS" in h["text"]
    assert "PATCH DRAFT" in h["text"]
    # pending_approval status → next action is about reviewing
    assert h["recommended_next_action"]


def test_handoff_package_type_debate_in_header(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    debate = store.create_debate(
        project_id="proj1", topic="T", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai",
    )
    result = svc.build_from_debate(debate_id=debate["debate_id"])
    assert "— DEBATE" in result["handoff"]["text"]


def test_handoff_package_type_execution_in_header(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    execution = store.create_execution(
        project_id="proj1",
        debate_id="",
        source_plan={"content": "Plan.", "topic": "T", "artifacts": []},
        proposal={"mode": "read_only_v1", "commands": None, "patch_draft": None, "imported_context": "", "source": {"artifacts": []}, "artifact_summary": ""},
    )
    result = svc.build_from_execution(execution_id=execution["execution_id"])
    assert "— EXECUTION" in result["handoff"]["text"]


def test_handoff_includes_mediation_key_differences(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    debate = store.create_debate(
        project_id="proj1", topic="Arch choice", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai",
    )
    mediation = {
        "participants": [
            {"label": "Debate A", "provider": "openai", "model": "gpt-4o",
             "latest": {"proposal": "Use microservices.", "rationale": "Scales well.", "risks": ["complexity"], "confidence": 0.85, "agreed": False}},
            {"label": "Debate B", "provider": "xai", "model": "grok-3",
             "latest": {"proposal": "Use a monolith.", "rationale": "Simpler.", "risks": ["scaling"], "confidence": 0.70, "agreed": False}},
        ],
        "key_differences": ["Debate A proposes: Use microservices.\nDebate B proposes: Use a monolith."],
        "recommended_next_step": "Review the judge plan.",
    }
    result = svc.build_from_debate(debate_id=debate["debate_id"], mediation=mediation)
    h = result["handoff"]
    text = h["text"]
    assert h["mediation"] is not None
    assert "MEDIATION INSIGHTS" in text
    assert "KEY DIFFERENCES" in text
    assert "Use microservices." in text
    assert "Use a monolith." in text
    assert "MEDIATION RECOMMENDED STEP" in text


def test_handoff_mediation_participant_positions_in_text(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    debate = store.create_debate(
        project_id="proj1", topic="T", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai",
    )
    mediation = {
        "participants": [
            {"label": "Debate A", "provider": "openai", "model": "gpt-4o",
             "latest": {"proposal": "Event sourcing.", "rationale": "Audit trail.", "risks": ["ops-overhead"], "confidence": 0.9, "agreed": True}},
        ],
        "key_differences": [],
        "recommended_next_step": "",
    }
    result = svc.build_from_debate(debate_id=debate["debate_id"], mediation=mediation)
    text = result["handoff"]["text"]
    assert "PARTICIPANT POSITIONS" in text
    assert "Debate A" in text
    assert "openai" in text
    assert "Event sourcing." in text
    assert "Confidence : 0.90  |  Agreed: yes" in text


def test_handoff_no_mediation_section_when_none(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    debate = store.create_debate(
        project_id="proj1", topic="T", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai",
    )
    result = svc.build_from_debate(debate_id=debate["debate_id"], mediation=None)
    assert "MEDIATION" not in result["handoff"]["text"]
    assert result["handoff"]["mediation"] is None


def test_handoff_mediation_snapshot_empty_participants_returns_none(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    debate = store.create_debate(
        project_id="proj1", topic="T", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai",
    )
    # Empty mediation (no participants, no differences) → snapshot is None
    result = svc.build_from_debate(debate_id=debate["debate_id"], mediation={"participants": [], "key_differences": [], "recommended_next_step": ""})
    assert result["handoff"]["mediation"] is None
    assert "MEDIATION" not in result["handoff"]["text"]


def test_handoff_project_instructions_separate_from_preferences(isolated_workspace_env):
    from workspace_ai.workspace_runtime.settings_service import SettingsService
    store = SessionStore(db_path=str(isolated_workspace_env))
    settings_svc = SettingsService(store=store)
    settings_svc.update({"personal_preferences": "Prefer Python.", "project_instructions": "Use pytest."})
    svc = HandoffService(store=store, settings_service=settings_svc)
    debate = store.create_debate(
        project_id="proj1", topic="T", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai",
    )
    result = svc.build_from_debate(debate_id=debate["debate_id"])
    text = result["handoff"]["text"]
    assert "PROJECT INSTRUCTIONS" in text
    assert "PERSONAL PREFERENCES" in text
    assert "Use pytest." in text
    assert "Prefer Python." in text
    # They must appear as distinct labels, not merged on one line
    instr_pos = text.index("PROJECT INSTRUCTIONS")
    prefs_pos = text.index("PERSONAL PREFERENCES")
    assert instr_pos != prefs_pos


def test_handoff_artifact_preview_appears_in_text(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    artifacts = [{"label": "models.py", "path": "models.py", "kind": "text", "size_bytes": 1024, "preview": "class User: pass"}]
    debate = store.create_debate(
        project_id="proj1", topic="T", bottlenecks="", files=artifacts, participants=[], max_rounds=1, judge_provider="openai",
    )
    result = svc.build_from_debate(debate_id=debate["debate_id"])
    text = result["handoff"]["text"]
    assert "models.py" in text
    assert "class User: pass" in text


def test_handoff_commands_have_dollar_prefix(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    execution = store.create_execution(
        project_id="proj1",
        debate_id="",
        source_plan={"content": "Plan.", "topic": "T", "artifacts": []},
        proposal={
            "mode": "change_plan_v1",
            "commands": ["pytest tests/", "git diff"],
            "patch_draft": None,
            "imported_context": "",
            "source": {"artifacts": []},
            "artifact_summary": "",
        },
    )
    result = svc.build_from_execution(execution_id=execution["execution_id"])
    text = result["handoff"]["text"]
    assert "  $ pytest tests/" in text
    assert "  $ git diff" in text


def test_handoff_judge_plan_section_label(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)
    debate = store.create_debate(
        project_id="proj1", topic="T", bottlenecks="", files=[], participants=[], max_rounds=1, judge_provider="openai",
    )
    result = svc.build_from_debate(debate_id=debate["debate_id"])
    assert "JUDGE PLAN" in result["handoff"]["text"]


def test_handoff_text_omits_empty_sections(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = HandoffService(store=store)

    debate = store.create_debate(
        project_id="proj1",
        topic="Minimal",
        bottlenecks="",
        files=[],
        participants=[],
        max_rounds=1,
        judge_provider="openai",
    )
    result = svc.build_from_debate(debate_id=debate["debate_id"])
    text = result["handoff"]["text"]
    assert "ARTIFACTS" not in text
    assert "ACTIVE CONTEXT IMPORTS" not in text
    assert "SUGGESTED COMMANDS" not in text
    assert "PATCH DRAFT" not in text
    assert "MEDIATION" not in text
