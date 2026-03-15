"""
Mirrors and validates the execution lifecycle completion surface helpers
defined in workspace_ai/ui/index.html:
  executionOutcomeSummary()
  renderExecutionStatusBand() label/class rules
  renderExecutionOutcome() output-tag rules

These are canonical specification tests.  JS rule changes must be
reflected here, and vice-versa.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Pure-Python mirrors
# ---------------------------------------------------------------------------

def execution_outcome_summary(execution: dict) -> dict:
    """Mirror of JS executionOutcomeSummary(execution)."""
    proposal = execution.get("proposal") or {}
    result = execution.get("execution") or {}
    mode = proposal.get("mode") or result.get("mode") or "read_only_v1"
    status = execution.get("status") or ""
    commands = (
        result.get("commands") if isinstance(result.get("commands"), list)
        else proposal.get("commands") if isinstance(proposal.get("commands"), list)
        else []
    )
    patch_plan = result.get("patch_plan") or proposal.get("patch_plan") or None
    patch_hunks = patch_plan.get("hunks", []) if isinstance(patch_plan, dict) else []
    patch_draft = (result.get("patch_draft") or proposal.get("patch_draft") or "").strip()
    proposal_steps = proposal.get("steps") if isinstance(proposal.get("steps"), list) else []
    result_steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    steps = result_steps if result_steps else proposal_steps
    return {
        "mode": mode,
        "status": status,
        "step_count": len(steps),
        "command_count": len(commands),
        "patch_hunk_count": len(patch_hunks),
        "has_patch_draft": bool(patch_draft),
        "has_execution_result": bool((result.get("result") or "").strip()),
        "rejection_note": (execution.get("approval_note") or "").strip(),
        "is_change_plan": mode == "change_plan_v1",
    }


def status_band_kind(execution: dict, summary: dict) -> str | None:
    """Returns 'pending' | 'completed' | 'rejected' | None — the CSS modifier."""
    status = execution.get("status") or ""
    if status == "pending_approval":
        return "pending"
    if status == "completed":
        return "completed"
    if status == "rejected":
        return "rejected"
    return None


def status_band_text(execution: dict, summary: dict) -> str | None:
    """Mirror of the text produced by renderExecutionStatusBand()."""
    status = execution.get("status") or ""
    s = summary
    mode_label = "change plan" if s["is_change_plan"] else "read-only review"
    step_count = s["step_count"]

    if status == "pending_approval":
        plural = "s" if step_count != 1 else ""
        return f"pending · {mode_label} · {step_count} step{plural} to review"

    if status == "completed":
        if s["is_change_plan"] and (s["command_count"] or s["patch_hunk_count"] or s["has_patch_draft"]):
            parts = []
            if s["command_count"]:
                parts.append(f"{s['command_count']} command{'s' if s['command_count'] != 1 else ''}")
            if s["patch_hunk_count"]:
                parts.append(f"{s['patch_hunk_count']} patch hunk{'s' if s['patch_hunk_count'] != 1 else ''}")
            if s["has_patch_draft"]:
                parts.append("patch draft")
            return f"completed · change plan · {' · '.join(parts)}"
        else:
            plural = "s" if step_count != 1 else ""
            return f"completed · {mode_label} · {step_count} step{plural} recorded"

    if status == "rejected":
        note = s["rejection_note"]
        return f"rejected{' · ' + note if note else ''}"

    return None


def outcome_tags(execution: dict, summary: dict) -> list[str]:
    """Mirror of the pill tags rendered by renderExecutionOutcome()."""
    if execution.get("status") != "completed":
        return []
    s = summary
    tags = []
    if s["command_count"]:
        tags.append(f"{s['command_count']} command{'s' if s['command_count'] != 1 else ''}")
    if s["patch_hunk_count"]:
        tags.append(f"{s['patch_hunk_count']} patch hunk{'s' if s['patch_hunk_count'] != 1 else ''}")
    if s["has_patch_draft"]:
        tags.append("patch draft")
    if not s["is_change_plan"] and s["step_count"]:
        tags.append(f"{s['step_count']} step{'s' if s['step_count'] != 1 else ''} reviewed")
    return tags


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _read_only_pending(step_count: int = 3) -> dict:
    steps = [{"step": i + 1, "summary": f"Step {i+1}", "status": "pending"} for i in range(step_count)]
    return {
        "status": "pending_approval",
        "approval_note": "",
        "proposal": {"mode": "read_only_v1", "steps": steps},
        "execution": {},
    }


def _read_only_completed(step_count: int = 3) -> dict:
    steps = [{"step": i + 1, "summary": f"Step {i+1}", "status": "reviewed",
              "result": "recorded"} for i in range(step_count)]
    return {
        "status": "completed",
        "approval_note": "lgtm",
        "proposal": {"mode": "read_only_v1", "steps": steps},
        "execution": {
            "mode": "read_only_v1",
            "result": "Execution approved and recorded.",
            "steps": steps,
        },
    }


def _change_plan_pending(commands: list[str] | None = None, hunk_count: int = 2) -> dict:
    cmds = commands or ["git add .", "git commit -m 'patch'"]
    hunks = [{"target": f"file_{i}.py", "change_summary": "edit"} for i in range(hunk_count)]
    steps = [{"step": 1, "summary": "Plan step", "status": "pending"}]
    return {
        "status": "pending_approval",
        "approval_note": "",
        "proposal": {
            "mode": "change_plan_v1",
            "steps": steps,
            "commands": cmds,
            "patch_plan": {"format": "unified", "hunks": hunks},
            "patch_draft": "--- a/file.py\n+++ b/file.py\n",
        },
        "execution": {},
    }


def _change_plan_completed(commands: list[str] | None = None, hunk_count: int = 2) -> dict:
    cmds = commands or ["git add .", "git commit -m 'patch'"]
    hunks = [{"target": f"file_{i}.py", "change_summary": "edit"} for i in range(hunk_count)]
    steps = [{"step": 1, "summary": "Plan step", "status": "planned", "result": "captured"}]
    return {
        "status": "completed",
        "approval_note": "approved",
        "proposal": {"mode": "change_plan_v1", "steps": steps},
        "execution": {
            "mode": "change_plan_v1",
            "result": "Execution approved as a concrete change plan.",
            "steps": steps,
            "commands": cmds,
            "patch_plan": {"format": "unified", "hunks": hunks},
            "patch_draft": "--- a/file.py\n+++ b/file.py\n",
        },
    }


def _rejected(note: str = "not ready") -> dict:
    return {
        "status": "rejected",
        "approval_note": note,
        "proposal": {"mode": "read_only_v1", "steps": []},
        "execution": {"mode": "read_only_v1", "result": "Execution was rejected."},
    }


# ---------------------------------------------------------------------------
# executionOutcomeSummary
# ---------------------------------------------------------------------------

class TestExecutionOutcomeSummary:
    def test_read_only_pending_mode(self):
        s = execution_outcome_summary(_read_only_pending())
        assert s["mode"] == "read_only_v1"
        assert s["is_change_plan"] is False
        assert s["status"] == "pending_approval"

    def test_read_only_pending_step_count(self):
        s = execution_outcome_summary(_read_only_pending(step_count=5))
        assert s["step_count"] == 5

    def test_read_only_completed_uses_result_steps(self):
        e = _read_only_completed(step_count=4)
        s = execution_outcome_summary(e)
        assert s["step_count"] == 4
        assert s["has_execution_result"] is True

    def test_change_plan_pending_command_count(self):
        e = _change_plan_pending(commands=["cmd1", "cmd2", "cmd3"])
        s = execution_outcome_summary(e)
        assert s["command_count"] == 3
        assert s["is_change_plan"] is True

    def test_change_plan_pending_patch_hunk_count(self):
        e = _change_plan_pending(hunk_count=3)
        s = execution_outcome_summary(e)
        assert s["patch_hunk_count"] == 3

    def test_change_plan_pending_has_patch_draft(self):
        e = _change_plan_pending()
        s = execution_outcome_summary(e)
        assert s["has_patch_draft"] is True

    def test_change_plan_completed_reads_result_commands(self):
        e = _change_plan_completed(commands=["a", "b"])
        s = execution_outcome_summary(e)
        assert s["command_count"] == 2

    def test_rejected_captures_note(self):
        s = execution_outcome_summary(_rejected("too risky"))
        assert s["rejection_note"] == "too risky"
        assert s["status"] == "rejected"

    def test_empty_execution_defaults(self):
        s = execution_outcome_summary({"status": "pending_approval", "proposal": {}, "execution": {}})
        assert s["step_count"] == 0
        assert s["command_count"] == 0
        assert s["patch_hunk_count"] == 0
        assert s["has_patch_draft"] is False
        assert s["has_execution_result"] is False


# ---------------------------------------------------------------------------
# Status band rules
# ---------------------------------------------------------------------------

class TestStatusBandKind:
    def test_pending_approval(self):
        e = _read_only_pending()
        assert status_band_kind(e, execution_outcome_summary(e)) == "pending"

    def test_completed(self):
        e = _read_only_completed()
        assert status_band_kind(e, execution_outcome_summary(e)) == "completed"

    def test_rejected(self):
        e = _rejected()
        assert status_band_kind(e, execution_outcome_summary(e)) == "rejected"

    def test_unknown_status_returns_none(self):
        e = {"status": "unknown", "proposal": {}, "execution": {}}
        assert status_band_kind(e, execution_outcome_summary(e)) is None


class TestStatusBandText:
    def test_pending_read_only_mentions_steps(self):
        e = _read_only_pending(step_count=2)
        text = status_band_text(e, execution_outcome_summary(e))
        assert text is not None
        assert "pending" in text
        assert "read-only review" in text
        assert "2 steps" in text

    def test_pending_single_step_no_plural(self):
        e = _read_only_pending(step_count=1)
        text = status_band_text(e, execution_outcome_summary(e))
        assert "1 step to review" in text

    def test_completed_read_only_mentions_steps_recorded(self):
        e = _read_only_completed(step_count=3)
        text = status_band_text(e, execution_outcome_summary(e))
        assert text is not None
        assert "completed" in text
        assert "3 steps recorded" in text

    def test_completed_change_plan_mentions_commands(self):
        e = _change_plan_completed(commands=["a", "b"])
        text = status_band_text(e, execution_outcome_summary(e))
        assert "completed" in text
        assert "change plan" in text
        assert "2 commands" in text

    def test_completed_change_plan_mentions_patch_hunks(self):
        e = _change_plan_completed(hunk_count=4)
        text = status_band_text(e, execution_outcome_summary(e))
        assert "4 patch hunks" in text

    def test_completed_change_plan_mentions_patch_draft(self):
        e = _change_plan_completed()
        text = status_band_text(e, execution_outcome_summary(e))
        assert "patch draft" in text

    def test_rejected_includes_note(self):
        e = _rejected("no approval yet")
        text = status_band_text(e, execution_outcome_summary(e))
        assert "rejected" in text
        assert "no approval yet" in text

    def test_rejected_no_note_no_bullet(self):
        e = _rejected("")
        text = status_band_text(e, execution_outcome_summary(e))
        assert text == "rejected"


# ---------------------------------------------------------------------------
# Outcome tags
# ---------------------------------------------------------------------------

class TestOutcomeTags:
    def test_pending_returns_empty(self):
        e = _read_only_pending()
        assert outcome_tags(e, execution_outcome_summary(e)) == []

    def test_rejected_returns_empty(self):
        e = _rejected()
        assert outcome_tags(e, execution_outcome_summary(e)) == []

    def test_read_only_completed_returns_steps_reviewed(self):
        e = _read_only_completed(step_count=3)
        tags = outcome_tags(e, execution_outcome_summary(e))
        assert any("reviewed" in t for t in tags)
        assert any("3" in t for t in tags)

    def test_change_plan_completed_returns_commands(self):
        e = _change_plan_completed(commands=["a", "b"])
        tags = outcome_tags(e, execution_outcome_summary(e))
        assert any("command" in t for t in tags)

    def test_change_plan_completed_returns_patch_hunks(self):
        e = _change_plan_completed(hunk_count=3)
        tags = outcome_tags(e, execution_outcome_summary(e))
        assert any("patch hunk" in t for t in tags)

    def test_change_plan_completed_returns_patch_draft(self):
        e = _change_plan_completed()
        tags = outcome_tags(e, execution_outcome_summary(e))
        assert "patch draft" in tags

    def test_change_plan_does_not_include_steps_reviewed_tag(self):
        e = _change_plan_completed()
        tags = outcome_tags(e, execution_outcome_summary(e))
        assert not any("reviewed" in t for t in tags)
