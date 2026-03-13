from __future__ import annotations

from workspace_ai.workspace_memory.session_store import SessionStore


def test_session_store_crud_and_checkpoint(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))

    session = store.create_session(project_id="workspace", title="Test session", mode="chat")
    assert session["project_id"] == "workspace"

    message = store.add_message(session_id=session["session_id"], role="user", content="hello")
    assert message["content"] == "hello"

    checkpoint = store.create_checkpoint(session_id=session["session_id"], summary="snap", state={"step": 1})
    assert checkpoint["summary"] == "snap"

    listed = store.list_sessions(project_id="workspace")
    assert len(listed) == 1

    assert store.delete_session(session_id=session["session_id"]) is True
    assert store.get_session(session["session_id"]) is None


def test_session_store_debate_roundtrip(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))

    debate = store.create_debate(
        project_id="forge",
        topic="Design debate",
        bottlenecks="Too many choices",
        files=["spec.md"],
        participants=[{"provider": "openai", "model": "gpt-5.4"}],
        judge_provider="openai",
    )
    assert debate["topic"] == "Design debate"

    round_payload = store.add_debate_round(
        debate_id=debate["debate_id"],
        round_index=1,
        participant_provider="openai",
        participant_model="gpt-5.4",
        response={"content": "Recommendation"},
    )
    assert round_payload["participant_provider"] == "openai"

    finalized = store.finalize_debate(
        debate_id=debate["debate_id"],
        final_plan={"content": "Final plan"},
        status="completed",
    )
    assert finalized is not None
    assert finalized["final_plan"]["content"] == "Final plan"
    assert len(finalized["rounds"]) == 1
