"""
Mirrors and validates the client-side debate search/filter logic defined in
workspace_ai/ui/index.html:
  matchesDebateFilter(debate, query)

These are canonical specification tests.  JS rule changes must be
reflected here, and vice-versa.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Pure-Python mirror
# ---------------------------------------------------------------------------

def matches_debate_filter(debate: dict, query: str, exec_by_debate: dict | None = None) -> bool:
    """Mirror of JS matchesDebateFilter(debate, query).

    ``exec_by_debate`` maps debate_id → execution dict, mirroring
    state.executionsByDebateId.
    """
    if not query:
        return True
    q = query.strip().lower()
    if not q:
        return True
    fields = [
        debate.get("topic") or "",
        debate.get("debate_id") or "",
        debate.get("status") or "",
        debate.get("debate_style") or "",
        debate.get("project_id") or "",
    ]
    if exec_by_debate:
        exec_rec = exec_by_debate.get(debate.get("debate_id") or "")
        if exec_rec:
            fields.append(exec_rec.get("status") or "")
    return any(q in f.lower() for f in fields)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _debate(
    topic: str = "Optimise the auth flow",
    status: str = "completed",
    debate_style: str = "standard",
    debate_id: str = "d-abc123",
    project_id: str = "forge",
) -> dict:
    return {
        "debate_id": debate_id,
        "topic": topic,
        "status": status,
        "debate_style": debate_style,
        "project_id": project_id,
    }


def _exec(status: str = "pending_approval", execution_id: str = "e-001") -> dict:
    return {"execution_id": execution_id, "status": status}


# ---------------------------------------------------------------------------
# Empty / no query
# ---------------------------------------------------------------------------

class TestEmptyQuery:
    def test_empty_string_matches_all(self):
        assert matches_debate_filter(_debate(), "") is True

    def test_whitespace_only_matches_all(self):
        assert matches_debate_filter(_debate(), "   ") is True

    def test_none_like_empty_matches_all(self):
        assert matches_debate_filter(_debate(), "") is True


# ---------------------------------------------------------------------------
# Topic matching
# ---------------------------------------------------------------------------

class TestTopicMatch:
    def test_exact_topic_matches(self):
        d = _debate(topic="Optimise auth flow")
        assert matches_debate_filter(d, "Optimise auth flow") is True

    def test_partial_topic_matches(self):
        assert matches_debate_filter(_debate(topic="Optimise auth flow"), "auth") is True

    def test_case_insensitive_topic(self):
        assert matches_debate_filter(_debate(topic="Auth Flow"), "auth flow") is True

    def test_non_matching_topic_returns_false(self):
        assert matches_debate_filter(_debate(topic="Logging overhaul"), "auth") is False


# ---------------------------------------------------------------------------
# Status matching
# ---------------------------------------------------------------------------

class TestStatusMatch:
    def test_status_completed_matches(self):
        assert matches_debate_filter(_debate(status="completed"), "completed") is True

    def test_status_partial_match(self):
        assert matches_debate_filter(_debate(status="max_rounds"), "max") is True

    def test_status_pending_matches(self):
        assert matches_debate_filter(_debate(status="pending"), "pending") is True

    def test_wrong_status_does_not_match(self):
        assert matches_debate_filter(_debate(status="completed"), "pending") is False


# ---------------------------------------------------------------------------
# Style matching
# ---------------------------------------------------------------------------

class TestStyleMatch:
    def test_style_fast_matches(self):
        assert matches_debate_filter(_debate(debate_style="fast"), "fast") is True

    def test_style_harsh_reviewer_partial(self):
        assert matches_debate_filter(_debate(debate_style="harsh_reviewer"), "harsh") is True

    def test_standard_style_matches(self):
        assert matches_debate_filter(_debate(debate_style="standard"), "standard") is True


# ---------------------------------------------------------------------------
# Debate ID matching
# ---------------------------------------------------------------------------

class TestDebateIdMatch:
    def test_full_debate_id_matches(self):
        assert matches_debate_filter(_debate(debate_id="d-abc123"), "d-abc123") is True

    def test_partial_debate_id_matches(self):
        assert matches_debate_filter(_debate(debate_id="d-abc123"), "abc") is True

    def test_wrong_id_does_not_match(self):
        assert matches_debate_filter(_debate(debate_id="d-abc123"), "xyz") is False


# ---------------------------------------------------------------------------
# Project ID matching
# ---------------------------------------------------------------------------

class TestProjectIdMatch:
    def test_project_id_matches(self):
        assert matches_debate_filter(_debate(project_id="myproject"), "myproject") is True

    def test_project_id_partial_matches(self):
        assert matches_debate_filter(_debate(project_id="my-forge-project"), "forge") is True


# ---------------------------------------------------------------------------
# Execution status matching
# ---------------------------------------------------------------------------

class TestExecutionStatusMatch:
    def test_linked_execution_status_matches(self):
        d = _debate(debate_id="d1")
        execs = {"d1": _exec(status="pending_approval")}
        assert matches_debate_filter(d, "pending_approval", execs) is True

    def test_linked_execution_status_partial_matches(self):
        d = _debate(debate_id="d1")
        execs = {"d1": _exec(status="pending_approval")}
        assert matches_debate_filter(d, "pending", execs) is True

    def test_no_execution_does_not_match_exec_status(self):
        d = _debate(debate_id="d1", status="completed")
        assert matches_debate_filter(d, "pending_approval") is False

    def test_other_debate_execution_not_used(self):
        d = _debate(debate_id="d1")
        execs = {"d2": _exec(status="pending_approval")}  # d2 not d1
        assert matches_debate_filter(d, "pending_approval", execs) is False

    def test_completed_execution_matches(self):
        d = _debate(debate_id="d1")
        execs = {"d1": _exec(status="completed")}
        assert matches_debate_filter(d, "completed", execs) is True


# ---------------------------------------------------------------------------
# Multi-field (first matching field wins)
# ---------------------------------------------------------------------------

class TestMultiField:
    def test_query_matches_topic_even_if_status_doesnt(self):
        d = _debate(topic="auth refactor", status="failed")
        assert matches_debate_filter(d, "auth") is True

    def test_query_matches_status_even_if_topic_doesnt(self):
        d = _debate(topic="unrelated topic", status="max_rounds")
        assert matches_debate_filter(d, "max_rounds") is True

    def test_nothing_matches_returns_false(self):
        d = _debate(topic="cache invalidation", status="completed", debate_style="standard",
                    debate_id="d-111", project_id="myproject")
        assert matches_debate_filter(d, "zzz_no_match_zzz") is False
