from __future__ import annotations

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.mediation_service import MediationService


def _make_debate(store: SessionStore, *, topic: str = "Test topic") -> dict:
    return store.create_debate(
        project_id="proj1",
        topic=topic,
        bottlenecks="",
        files=[],
        participants=[{"provider": "openai", "model": "gpt-4o"}, {"provider": "xai", "model": "grok-3"}],
        max_rounds=2,
        judge_provider="openai",
    )


def _add_round(store: SessionStore, *, debate_id: str, round_index: int, provider: str, model: str, proposal: str, rationale: str, risks: list, confidence: float, agreed: bool) -> None:
    store.add_debate_round(
        debate_id=debate_id,
        round_index=round_index,
        participant_provider=provider,
        participant_model=model,
        response={
            "content": proposal,
            "provider": provider,
            "model": model,
            "mode": "mock",
            "usage": {},
            "structured": {
                "proposal": proposal,
                "rationale": rationale,
                "risks": risks,
                "confidence": confidence,
                "agreed": agreed,
            },
        },
    )


def test_not_found(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    result = svc.get_mediation(debate_id="deb_missing")
    assert result["status"] == "not_found"


def test_empty_debate_has_no_participants(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    result = svc.get_mediation(debate_id=debate["debate_id"])
    assert result["status"] == "ok"
    med = result["mediation"]
    assert med["participants"] == []
    assert med["key_differences"] == []


def test_groups_rounds_by_participant(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]

    _add_round(store, debate_id=debate_id, round_index=1, provider="openai", model="gpt-4o",
               proposal="Use microservices.", rationale="Scalable.", risks=["complexity"], confidence=0.8, agreed=False)
    _add_round(store, debate_id=debate_id, round_index=1, provider="xai", model="grok-3",
               proposal="Use a monolith.", rationale="Simpler ops.", risks=["scaling"], confidence=0.75, agreed=False)

    result = svc.get_mediation(debate_id=debate_id)
    med = result["mediation"]
    assert len(med["participants"]) == 2
    assert med["participants"][0]["label"] == "Debate A"
    assert med["participants"][0]["provider"] == "openai"
    assert med["participants"][1]["label"] == "Debate B"
    assert med["participants"][1]["provider"] == "xai"
    assert med["participants"][0]["latest"]["proposal"] == "Use microservices."
    assert med["participants"][1]["latest"]["proposal"] == "Use a monolith."


def test_latest_round_reflects_last_submission(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]

    _add_round(store, debate_id=debate_id, round_index=1, provider="openai", model="gpt-4o",
               proposal="Initial proposal.", rationale="Early.", risks=[], confidence=0.5, agreed=False)
    _add_round(store, debate_id=debate_id, round_index=2, provider="openai", model="gpt-4o",
               proposal="Revised proposal.", rationale="Updated.", risks=["r1"], confidence=0.85, agreed=True)

    result = svc.get_mediation(debate_id=debate_id)
    med = result["mediation"]
    assert len(med["participants"]) == 1
    latest = med["participants"][0]["latest"]
    assert latest["proposal"] == "Revised proposal."
    assert latest["agreed"] is True
    assert latest["confidence"] == 0.85


def test_key_differences_diverging_proposals(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]

    _add_round(store, debate_id=debate_id, round_index=1, provider="openai", model="gpt-4o",
               proposal="Adopt event-driven architecture with Kafka.", rationale="Async decoupling.",
               risks=["ops complexity"], confidence=0.9, agreed=False)
    _add_round(store, debate_id=debate_id, round_index=1, provider="xai", model="grok-3",
               proposal="Keep synchronous REST APIs and optimize with caching.", rationale="Simpler stack.",
               risks=["latency"], confidence=0.7, agreed=False)

    result = svc.get_mediation(debate_id=debate_id)
    diffs = result["mediation"]["key_differences"]
    assert any("Debate A proposes" in d for d in diffs)
    assert any("Debate B proposes" in d for d in diffs)


def test_key_differences_risk_asymmetry(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]

    _add_round(store, debate_id=debate_id, round_index=1, provider="openai", model="gpt-4o",
               proposal="Same proposal.", rationale="R.", risks=["vendor lock-in", "cost"], confidence=0.8, agreed=False)
    _add_round(store, debate_id=debate_id, round_index=1, provider="xai", model="grok-3",
               proposal="Same proposal.", rationale="R.", risks=["latency"], confidence=0.8, agreed=False)

    result = svc.get_mediation(debate_id=debate_id)
    diffs = result["mediation"]["key_differences"]
    assert any("Debate A" in d and "vendor lock-in" in d.lower() or "cost" in d.lower() for d in diffs)
    assert any("Debate B" in d and "latency" in d for d in diffs)


def test_key_differences_confidence_divergence(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]

    _add_round(store, debate_id=debate_id, round_index=1, provider="openai", model="gpt-4o",
               proposal="Plan X.", rationale="R.", risks=[], confidence=0.95, agreed=False)
    _add_round(store, debate_id=debate_id, round_index=1, provider="xai", model="grok-3",
               proposal="Plan X.", rationale="R.", risks=[], confidence=0.55, agreed=False)

    result = svc.get_mediation(debate_id=debate_id)
    diffs = result["mediation"]["key_differences"]
    assert any("Confidence divergence" in d for d in diffs)


def test_key_differences_agreement_mismatch(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]

    _add_round(store, debate_id=debate_id, round_index=1, provider="openai", model="gpt-4o",
               proposal="Plan X.", rationale="R.", risks=[], confidence=0.8, agreed=True)
    _add_round(store, debate_id=debate_id, round_index=1, provider="xai", model="grok-3",
               proposal="Plan X.", rationale="R.", risks=[], confidence=0.8, agreed=False)

    result = svc.get_mediation(debate_id=debate_id)
    diffs = result["mediation"]["key_differences"]
    assert any("Agreement mismatch" in d for d in diffs)


def test_no_differences_when_participants_agree(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]

    # Identical proposals, risks, confidence, agreed state
    for provider in ("openai", "xai"):
        _add_round(store, debate_id=debate_id, round_index=1, provider=provider, model="m",
                   proposal="Build with hexagonal architecture.", rationale="R.",
                   risks=["shared-risk"], confidence=0.8, agreed=True)

    result = svc.get_mediation(debate_id=debate_id)
    diffs = result["mediation"]["key_differences"]
    assert any("No significant differences" in d for d in diffs)


def test_judge_extracted_from_final_plan(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]
    store.finalize_debate(
        debate_id=debate_id,
        final_plan={
            "provider": "openai",
            "model": "gpt-4o",
            "content": "Final plan text.",
            "mode": "mock",
            "usage": {},
            "structured": {
                "plan": "Adopt event sourcing.",
                "rationale": "Audit trail.",
                "risks": ["complexity"],
                "confidence": 0.92,
                "agreed": True,
            },
        },
        status="completed",
    )
    result = svc.get_mediation(debate_id=debate_id)
    judge = result["mediation"]["judge"]
    assert judge["plan"] == "Adopt event sourcing."
    assert judge["confidence"] == 0.92
    assert judge["agreed"] is True


def test_recommended_next_step_completed(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]
    store.finalize_debate(
        debate_id=debate_id,
        final_plan={
            "structured": {"plan": "Do X.", "rationale": "", "risks": [], "confidence": 0.9, "agreed": True}
        },
        status="completed",
    )
    result = svc.get_mediation(debate_id=debate_id)
    step = result["mediation"]["recommended_next_step"]
    assert "execution" in step.lower() or "plan" in step.lower()


def test_recommended_next_step_failed(isolated_workspace_env):
    store = SessionStore(db_path=str(isolated_workspace_env))
    svc = MediationService(store=store)
    debate = _make_debate(store)
    debate_id = debate["debate_id"]
    store.finalize_debate(debate_id=debate_id, final_plan={}, status="failed")
    result = svc.get_mediation(debate_id=debate_id)
    step = result["mediation"]["recommended_next_step"]
    assert "failed" in step.lower()
