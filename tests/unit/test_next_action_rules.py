"""
Mirrors and validates the next-action recommendation rules defined in
workspace_ai/ui/index.html (debateNextAction / executionNextAction).

These tests are a canonical specification.  If you change the JS rules
you must update the expectations here, and vice-versa.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Pure-Python mirrors of the JS recommendation functions
# ---------------------------------------------------------------------------

def debate_next_action(debate: dict, execution: dict | None = None) -> dict | None:
    """Mirror of JS debateNextAction(debate).

    ``execution`` corresponds to state.executionsByDebateId[debateId].
    """
    status = debate.get("status", "")
    debate_id = debate.get("debate_id", "")

    if status in ("pending", "running"):
        return {"label": "Running\u2026", "kind": "running", "disabled": True, "debateId": debate_id}

    terminal = status in ("completed", "max_rounds", "failed")
    if not terminal:
        return None

    if status == "failed":
        return None  # card shows failed; no clear recoverable next step

    if execution is None:
        return {"label": "Create Execution", "kind": "create_execution", "debateId": debate_id}

    exec_status = execution.get("status", "")

    if exec_status == "pending_approval":
        return {"label": "Review & Approve", "kind": "review_execution", "debateId": debate_id}

    if exec_status == "completed":
        return {
            "label": "Export Result",
            "kind": "export_result",
            "debateId": debate_id,
            "executionId": execution.get("execution_id"),
        }

    if exec_status == "rejected":
        return {"label": "New Execution", "kind": "create_execution", "debateId": debate_id}

    return {"label": "Open Handoff", "kind": "open_handoff", "debateId": debate_id}


def execution_next_action(execution: dict) -> dict | None:
    """Mirror of JS executionNextAction(execution)."""
    status = execution.get("status", "")
    execution_id = execution.get("execution_id", "")

    if status == "pending_approval":
        return {"label": "Approve", "kind": "approve_execution", "executionId": execution_id}

    if status == "completed":
        return {"label": "Export Result", "kind": "export_result", "executionId": execution_id}

    if status == "rejected":
        return {"label": "New Execution", "kind": "new_execution", "executionId": None}

    return None


# ---------------------------------------------------------------------------
# Debate next-action rules
# ---------------------------------------------------------------------------

def _debate(status: str, debate_id: str = "d1") -> dict:
    return {"debate_id": debate_id, "status": status, "final_plan": {"content": "plan"}}


def _execution(status: str, execution_id: str = "e1") -> dict:
    return {"execution_id": execution_id, "status": status}


class TestDebateNextAction:
    def test_pending_returns_running_disabled(self):
        action = debate_next_action(_debate("pending"))
        assert action is not None
        assert action["kind"] == "running"
        assert action["disabled"] is True
        assert action["label"] == "Running\u2026"

    def test_running_returns_running_disabled(self):
        action = debate_next_action(_debate("running"))
        assert action is not None
        assert action["kind"] == "running"
        assert action["disabled"] is True

    def test_failed_returns_none(self):
        assert debate_next_action(_debate("failed")) is None

    def test_completed_no_execution_returns_create_execution(self):
        action = debate_next_action(_debate("completed"), execution=None)
        assert action is not None
        assert action["kind"] == "create_execution"
        assert action["label"] == "Create Execution"

    def test_max_rounds_no_execution_returns_create_execution(self):
        action = debate_next_action(_debate("max_rounds"), execution=None)
        assert action is not None
        assert action["kind"] == "create_execution"

    def test_completed_with_pending_approval_execution_returns_review(self):
        action = debate_next_action(_debate("completed"), execution=_execution("pending_approval"))
        assert action is not None
        assert action["kind"] == "review_execution"
        assert "Approve" in action["label"]

    def test_completed_with_completed_execution_returns_export(self):
        action = debate_next_action(_debate("completed"), execution=_execution("completed", "e99"))
        assert action is not None
        assert action["kind"] == "export_result"
        assert action["executionId"] == "e99"
        assert action["label"] == "Export Result"

    def test_completed_with_rejected_execution_returns_new_execution(self):
        action = debate_next_action(_debate("completed"), execution=_execution("rejected"))
        assert action is not None
        assert action["kind"] == "create_execution"
        assert action["label"] == "New Execution"

    def test_completed_with_unknown_execution_status_returns_open_handoff(self):
        action = debate_next_action(_debate("completed"), execution=_execution("some_other_status"))
        assert action is not None
        assert action["kind"] == "open_handoff"

    def test_debate_id_is_propagated(self):
        action = debate_next_action(_debate("completed", "debate-xyz"), execution=None)
        assert action["debateId"] == "debate-xyz"

    def test_unknown_status_returns_none(self):
        assert debate_next_action(_debate("unknown_status")) is None


# ---------------------------------------------------------------------------
# Execution next-action rules
# ---------------------------------------------------------------------------

class TestExecutionNextAction:
    def test_pending_approval_returns_approve(self):
        action = execution_next_action(_execution("pending_approval", "e1"))
        assert action is not None
        assert action["kind"] == "approve_execution"
        assert action["label"] == "Approve"
        assert action["executionId"] == "e1"

    def test_completed_returns_export(self):
        action = execution_next_action(_execution("completed", "e2"))
        assert action is not None
        assert action["kind"] == "export_result"
        assert action["label"] == "Export Result"
        assert action["executionId"] == "e2"

    def test_rejected_returns_new_execution(self):
        action = execution_next_action(_execution("rejected", "e3"))
        assert action is not None
        assert action["kind"] == "new_execution"
        assert action["label"] == "New Execution"

    def test_unknown_status_returns_none(self):
        assert execution_next_action(_execution("some_other_status")) is None

    def test_empty_status_returns_none(self):
        assert execution_next_action({}) is None
