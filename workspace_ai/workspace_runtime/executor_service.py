from __future__ import annotations

from typing import Any, Dict, List

from workspace_ai.workspace_memory.session_store import SessionStore


class ExecutorService:
    def __init__(self, *, store: SessionStore) -> None:
        self.store = store

    def list_executions(self, *, project_id: str | None = None, limit: int = 50) -> Dict[str, Any]:
        rows = self.store.list_executions(project_id=project_id, limit=limit)
        return {"status": "ok", "count": len(rows), "executions": rows}

    def get_execution(self, *, execution_id: str) -> Dict[str, Any]:
        execution = self.store.get_execution(execution_id)
        if execution is None:
            return {"status": "not_found", "execution_id": execution_id}
        return {"status": "ok", "execution": execution}

    def create_execution(
        self,
        *,
        project_id: str,
        debate_id: str | None = None,
        plan: str = "",
    ) -> Dict[str, Any]:
        normalized_plan = str(plan or "").strip()
        normalized_debate_id = str(debate_id or "").strip()
        source_plan = self._source_plan(project_id=project_id, debate_id=normalized_debate_id, plan=normalized_plan)
        proposal = self._build_proposal(source_plan=source_plan)
        execution = self.store.create_execution(
            project_id=project_id,
            debate_id=normalized_debate_id,
            source_plan=source_plan,
            proposal=proposal,
        )
        return {"status": "ok", "execution": execution}

    def decide_execution(self, *, execution_id: str, approved: bool, note: str = "") -> Dict[str, Any]:
        execution = self.store.get_execution(execution_id)
        if execution is None:
            return {"status": "not_found", "execution_id": execution_id}
        current_status = str(execution.get("status") or "")
        if current_status != "pending_approval":
            raise ValueError(f"execution is not pending approval: {current_status}")
        if not approved:
            updated = self.store.update_execution(
                execution_id=execution_id,
                status="rejected",
                execution={
                    "mode": "read_only_v1",
                    "applied": False,
                    "result": "Execution was rejected before any actions ran.",
                    "steps": [],
                },
                approval_note=str(note or "").strip(),
            )
            return {"status": "ok", "execution": updated}
        result = self._execute_read_only(execution=execution, note=note)
        updated = self.store.update_execution(
            execution_id=execution_id,
            status="completed",
            execution=result,
            approval_note=str(note or "").strip(),
        )
        return {"status": "ok", "execution": updated}

    def _source_plan(self, *, project_id: str, debate_id: str, plan: str) -> Dict[str, Any]:
        if debate_id:
            debate = self.store.get_debate(debate_id)
            if debate is None:
                raise ValueError(f"debate not found: {debate_id}")
            final_plan = debate.get("final_plan") if isinstance(debate.get("final_plan"), dict) else {}
            content = str(final_plan.get("content") or "").strip()
            if not content:
                raise ValueError(f"debate has no final plan to execute: {debate_id}")
            return {
                "project_id": str(debate.get("project_id") or project_id),
                "debate_id": debate_id,
                "content": content,
                "provider": final_plan.get("provider"),
                "model": final_plan.get("model"),
                "topic": str(debate.get("topic") or ""),
            }
        if not plan:
            raise ValueError("execution requires either debate_id or plan")
        return {"project_id": project_id, "debate_id": "", "content": plan, "provider": "workspace", "model": None, "topic": ""}

    def _build_proposal(self, *, source_plan: Dict[str, Any]) -> Dict[str, Any]:
        plan_text = str(source_plan.get("content") or "").strip()
        steps = self._extract_steps(plan_text)
        summary = steps[0]["summary"] if steps else (plan_text[:240] or "No plan summary available.")
        return {
            "mode": "read_only_v1",
            "summary": summary,
            "requires_approval": True,
            "action_type": "review",
            "steps": steps,
            "source": {
                "debate_id": source_plan.get("debate_id") or "",
                "provider": source_plan.get("provider"),
                "model": source_plan.get("model"),
                "topic": source_plan.get("topic") or "",
            },
        }

    def _extract_steps(self, plan_text: str) -> List[Dict[str, Any]]:
        raw_lines = [line.strip(" -*\t") for line in plan_text.splitlines() if line.strip()]
        if not raw_lines:
            raw_lines = [segment.strip() for segment in plan_text.split(".") if segment.strip()]
        steps: List[Dict[str, Any]] = []
        for index, line in enumerate(raw_lines[:8], start=1):
            steps.append(
                {
                    "step": index,
                    "summary": line[:240],
                    "status": "pending",
                }
            )
        return steps

    def _execute_read_only(self, *, execution: Dict[str, Any], note: str) -> Dict[str, Any]:
        proposal = execution.get("proposal") if isinstance(execution.get("proposal"), dict) else {}
        steps = proposal.get("steps") if isinstance(proposal.get("steps"), list) else []
        reviewed_steps = []
        for item in steps:
            if not isinstance(item, dict):
                continue
            reviewed_steps.append(
                {
                    **item,
                    "status": "reviewed",
                    "result": "Recorded for manual execution; read-only mode did not run shell commands.",
                }
            )
        return {
            "mode": "read_only_v1",
            "applied": False,
            "result": "Execution approved and recorded. Read-only mode does not mutate the workspace.",
            "review_note": str(note or "").strip(),
            "steps": reviewed_steps,
        }
