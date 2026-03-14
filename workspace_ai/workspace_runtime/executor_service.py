from __future__ import annotations

import re
from typing import Any, Dict, List

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.context_import_service import ContextImportService


class ExecutorService:
    ALLOWED_MODES = {"read_only_v1", "change_plan_v1"}

    def __init__(self, *, store: SessionStore) -> None:
        self.store = store
        self.context_import_service = ContextImportService(store=store)

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
        execution_mode: str = "read_only_v1",
        context_import_ids: List[str] | None = None,
    ) -> Dict[str, Any]:
        normalized_plan = str(plan or "").strip()
        normalized_debate_id = str(debate_id or "").strip()
        normalized_mode = self._normalize_mode(execution_mode)
        resolved_import_ids = self._resolve_context_import_ids(project_id=project_id, import_ids=context_import_ids)
        source_plan = self._source_plan(project_id=project_id, debate_id=normalized_debate_id, plan=normalized_plan)
        imported_context = self._build_imported_context(project_id=project_id, import_ids=resolved_import_ids)
        proposal = self._build_proposal(source_plan=source_plan, execution_mode=normalized_mode, imported_context=imported_context)
        execution = self.store.create_execution(
            project_id=project_id,
            debate_id=normalized_debate_id,
            source_plan=source_plan,
            proposal=proposal,
            context_import_ids=resolved_import_ids,
        )
        return {"status": "ok", "execution": execution}

    def _resolve_context_import_ids(self, *, project_id: str, import_ids: List[str] | None) -> List[str]:
        if not import_ids:
            return []
        self.context_import_service.resolve_import_ids(project_id=project_id, import_ids=import_ids)
        return list(import_ids)

    def _build_imported_context(self, *, project_id: str, import_ids: List[str]) -> str:
        if import_ids:
            return self.context_import_service.build_context_block_for_ids(project_id=project_id, import_ids=import_ids)
        return self.context_import_service.build_context_block(project_id=project_id)

    def decide_execution(self, *, execution_id: str, approved: bool, note: str = "") -> Dict[str, Any]:
        execution = self.store.get_execution(execution_id)
        if execution is None:
            return {"status": "not_found", "execution_id": execution_id}
        current_status = str(execution.get("status") or "")
        if current_status != "pending_approval":
            raise ValueError(f"execution is not pending approval: {current_status}")
        proposal = execution.get("proposal") if isinstance(execution.get("proposal"), dict) else {}
        proposal_mode = self._normalize_mode(str(proposal.get("mode") or "read_only_v1"))
        if not approved:
            updated = self.store.update_execution(
                execution_id=execution_id,
                status="rejected",
                execution={
                    "mode": proposal_mode,
                    "applied": False,
                    "result": "Execution was rejected before any actions ran.",
                    "commands": proposal.get("commands", []) if isinstance(proposal.get("commands"), list) else [],
                    "patch_plan": proposal.get("patch_plan", {}) if isinstance(proposal.get("patch_plan"), dict) else {},
                    "patch_draft": str(proposal.get("patch_draft") or "").strip(),
                    "steps": [],
                },
                approval_note=str(note or "").strip(),
            )
            return {"status": "ok", "execution": updated}
        if proposal_mode == "change_plan_v1":
            result = self._execute_change_plan(execution=execution, note=note)
        else:
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
            artifacts = debate.get("files") if isinstance(debate.get("files"), list) else []
            return {
                "project_id": str(debate.get("project_id") or project_id),
                "debate_id": debate_id,
                "content": content,
                "provider": final_plan.get("provider"),
                "model": final_plan.get("model"),
                "topic": str(debate.get("topic") or ""),
                "artifacts": artifacts,
            }
        if not plan:
            raise ValueError("execution requires either debate_id or plan")
        return {
            "project_id": project_id,
            "debate_id": "",
            "content": plan,
            "provider": "workspace",
            "model": None,
            "topic": "",
            "artifacts": [],
        }

    def _build_proposal(self, *, source_plan: Dict[str, Any], execution_mode: str, imported_context: str = "") -> Dict[str, Any]:
        plan_text = str(source_plan.get("content") or "").strip()
        steps = self._extract_steps(plan_text)
        summary = steps[0]["summary"] if steps else (plan_text[:240] or "No plan summary available.")
        artifacts = source_plan.get("artifacts") if isinstance(source_plan.get("artifacts"), list) else []
        proposal = {
            "mode": execution_mode,
            "summary": summary,
            "artifact_summary": self._artifact_summary(artifacts),
            "imported_context": imported_context,
            "requires_approval": True,
            "action_type": "review" if execution_mode == "read_only_v1" else "change_plan",
            "steps": steps,
            "source": {
                "debate_id": source_plan.get("debate_id") or "",
                "provider": source_plan.get("provider"),
                "model": source_plan.get("model"),
                "topic": source_plan.get("topic") or "",
                "artifacts": artifacts,
            },
        }
        if execution_mode == "change_plan_v1":
            proposal["commands"] = self._suggest_commands(source_plan=source_plan, steps=steps)
            proposal["patch_plan"] = self._build_patch_plan(source_plan=source_plan, steps=steps)
            proposal["patch_draft"] = self._render_patch_draft(proposal["patch_plan"])
        return proposal

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
            "artifacts": proposal.get("source", {}).get("artifacts", []) if isinstance(proposal.get("source"), dict) else [],
            "steps": reviewed_steps,
        }

    def _execute_change_plan(self, *, execution: Dict[str, Any], note: str) -> Dict[str, Any]:
        proposal = execution.get("proposal") if isinstance(execution.get("proposal"), dict) else {}
        steps = proposal.get("steps") if isinstance(proposal.get("steps"), list) else []
        planned_steps = []
        for item in steps:
            if not isinstance(item, dict):
                continue
            planned_steps.append(
                {
                    **item,
                    "status": "planned",
                    "result": "Captured as part of a concrete non-executing change plan.",
                }
            )
        return {
            "mode": "change_plan_v1",
            "applied": False,
            "result": "Execution approved as a concrete change plan. Forge prepared commands and a patch outline without applying them.",
            "review_note": str(note or "").strip(),
            "artifacts": proposal.get("source", {}).get("artifacts", []) if isinstance(proposal.get("source"), dict) else [],
            "commands": proposal.get("commands", []) if isinstance(proposal.get("commands"), list) else [],
            "patch_plan": proposal.get("patch_plan", {}) if isinstance(proposal.get("patch_plan"), dict) else {},
            "patch_draft": str(proposal.get("patch_draft") or "").strip(),
            "steps": planned_steps,
        }

    @classmethod
    def _normalize_mode(cls, execution_mode: str) -> str:
        normalized = str(execution_mode or "read_only_v1").strip().lower()
        if normalized not in cls.ALLOWED_MODES:
            raise ValueError(f"execution_mode must be one of: {', '.join(sorted(cls.ALLOWED_MODES))}")
        return normalized

    def _suggest_commands(self, *, source_plan: Dict[str, Any], steps: List[Dict[str, Any]]) -> List[str]:
        artifacts = source_plan.get("artifacts") if isinstance(source_plan.get("artifacts"), list) else []
        targets = self._suggest_targets(source_plan=source_plan, steps=steps)
        labels = [target["path"] for target in targets if str(target.get("path") or "").strip()]
        commands: List[str] = []
        for test_target in self._suggest_test_targets(source_plan=source_plan, steps=steps, targets=targets):
            commands.append(f"pytest {test_target} -q")
        if labels:
            search_terms = self._search_terms(source_plan=source_plan, steps=steps, labels=labels)
            commands.append(f"rg -n \"{search_terms}\" {' '.join(labels[:3])}")
        if not any(command == "pytest -q" for command in commands):
            commands.append("pytest -q")
        return commands[:3]

    def _build_patch_plan(self, *, source_plan: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        suggested_targets = self._suggest_targets(source_plan=source_plan, steps=steps)
        targets = [str(target.get("path") or "[select target file]").strip() for target in suggested_targets[:3]] or ["[select target file]"]
        hunks = []
        for index, target in enumerate(suggested_targets[:3], start=1):
            summary = steps[min(index - 1, len(steps) - 1)]["summary"] if steps else "Apply the approved change."
            hunks.append(
                {
                    "target": str(target.get("path") or "[select target file]").strip(),
                    "change_summary": summary,
                    "reason": str(target.get("reason") or "Matched from debate artifacts and plan text.").strip(),
                }
            )
        if not hunks:
            for index, target in enumerate(targets, start=1):
                summary = steps[min(index - 1, len(steps) - 1)]["summary"] if steps else "Apply the approved change."
                hunks.append({"target": target, "change_summary": summary, "reason": "No concrete repo target inferred."})
        return {
            "format": "manual_patch_outline_v1",
            "targets": targets,
            "hunks": hunks,
        }

    def _render_patch_draft(self, patch_plan: Dict[str, Any]) -> str:
        hunks = patch_plan.get("hunks") if isinstance(patch_plan.get("hunks"), list) else []
        if not hunks:
            return ""
        lines: List[str] = ["*** Begin Patch"]
        for hunk in hunks:
            if not isinstance(hunk, dict):
                continue
            target = str(hunk.get("target") or "[select target file]").strip()
            summary = str(hunk.get("change_summary") or "Apply the planned change.").strip()
            reason = str(hunk.get("reason") or "").strip()
            lines.extend(
                [
                    f"*** Update File: {target}",
                    "@@",
                    f"# Change summary: {summary}",
                    f"# Reason: {reason or 'Planned from approved execution.'}",
                    "",
                ]
            )
        lines.append("*** End Patch")
        return "\n".join(lines).strip()

    def _suggest_targets(self, *, source_plan: Dict[str, Any], steps: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        artifacts = source_plan.get("artifacts") if isinstance(source_plan.get("artifacts"), list) else []
        plan_text = " ".join(str(step.get("summary") or "").strip() for step in steps).lower()
        suggestions: List[Dict[str, str]] = []
        seen: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path") or artifact.get("label") or "").strip()
            label = str(artifact.get("label") or path).strip()
            if not path or path in seen:
                continue
            reason = "Referenced artifact from the debate context."
            lower_path = path.lower()
            lower_label = label.lower()
            if any(token in plan_text for token in self._tokens_from_path(lower_label)):
                reason = "Artifact name matched the approved plan text."
            suggestions.append({"path": path, "reason": reason})
            seen.add(path)
        derived = self._derive_targets_from_plan(plan_text)
        for path, reason in derived:
            if path in seen:
                for suggestion in suggestions:
                    if str(suggestion.get("path") or "") == path and reason not in str(suggestion.get("reason") or ""):
                        suggestion["reason"] = f"{suggestion['reason']} {reason}".strip()
                continue
            suggestions.append({"path": path, "reason": reason})
            seen.add(path)
        return suggestions

    @staticmethod
    def _tokens_from_path(value: str) -> List[str]:
        return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) >= 3]

    def _derive_targets_from_plan(self, plan_text: str) -> List[tuple[str, str]]:
        suggestions: List[tuple[str, str]] = []
        if "ui" in plan_text or "frontend" in plan_text or "panel" in plan_text:
            suggestions.append(("workspace_ai/ui/index.html", "Plan mentions debate UI work."))
        if "router" in plan_text or "route" in plan_text or "endpoint" in plan_text or "api" in plan_text:
            suggestions.append(("workspace_ai/workspace_api/router.py", "Plan mentions API or routing changes."))
        if "model" in plan_text or "request" in plan_text or "payload" in plan_text or "validation" in plan_text:
            suggestions.append(("workspace_ai/workspace_api/models.py", "Plan mentions request or model shape changes."))
        if "executor" in plan_text or "execution" in plan_text or "change plan" in plan_text or "mode" in plan_text:
            suggestions.append(("workspace_ai/workspace_runtime/executor_service.py", "Plan mentions execution behavior."))
        if "debate" in plan_text and ("service" in plan_text or "judge" in plan_text or "structured" in plan_text):
            suggestions.append(("workspace_ai/workspace_runtime/debate_service.py", "Plan mentions debate service behavior."))
        if "session" in plan_text or "manager" in plan_text:
            suggestions.append(("workspace_ai/workspace_runtime/session_manager.py", "Plan mentions session manager flow."))
        if "store" in plan_text or "sqlite" in plan_text or "persist" in plan_text:
            suggestions.append(("workspace_ai/workspace_memory/session_store.py", "Plan mentions persistence changes."))
        return suggestions

    def _suggest_test_targets(self, *, source_plan: Dict[str, Any], steps: List[Dict[str, Any]], targets: List[Dict[str, str]]) -> List[str]:
        plan_text = " ".join(str(step.get("summary") or "").strip() for step in steps).lower()
        test_targets: List[str] = []
        if (
            any(
                str(target.get("path") or "") in {
                    "workspace_ai/ui/index.html",
                    "workspace_ai/workspace_api/router.py",
                    "workspace_ai/workspace_api/models.py",
                }
                for target in targets
            )
            or "ui" in plan_text
            or "api" in plan_text
            or "router" in plan_text
            or "endpoint" in plan_text
        ):
            test_targets.append("tests/integration/test_sessions_api.py")
        if any("workspace_ai/workspace_runtime/executor_service.py" == str(target.get("path") or "") for target in targets) or "execution" in plan_text or "executor" in plan_text:
            test_targets.append("tests/unit/test_executor_service.py")
        if any("workspace_ai/workspace_runtime/debate_service.py" == str(target.get("path") or "") for target in targets) or "debate" in plan_text:
            test_targets.append("tests/unit/test_debate_service.py")
        if any("workspace_ai/workspace_memory/session_store.py" == str(target.get("path") or "") for target in targets) or "store" in plan_text or "persist" in plan_text:
            test_targets.append("tests/unit/test_session_store.py")
        deduped: List[str] = []
        for target in test_targets:
            if target not in deduped:
                deduped.append(target)
        return deduped[:2]

    def _search_terms(self, *, source_plan: Dict[str, Any], steps: List[Dict[str, Any]], labels: List[str]) -> str:
        keywords = ["TODO", "FIXME"]
        for step in steps[:3]:
            summary = str(step.get("summary") or "").strip()
            for token in self._tokens_from_path(summary):
                if token not in keywords:
                    keywords.append(token)
                    break
        if labels:
            base = labels[0].rsplit("/", 1)[-1].split(".", 1)[0]
            for token in self._tokens_from_path(base):
                if token not in keywords:
                    keywords.append(token)
                    break
        return "|".join(keywords[:4])

    @staticmethod
    def _artifact_summary(artifacts: List[Dict[str, Any]]) -> str:
        if not artifacts:
            return "No artifacts attached."
        rows: List[str] = []
        for artifact in artifacts[:5]:
            if not isinstance(artifact, dict):
                continue
            label = str(artifact.get("label") or artifact.get("path") or "artifact").strip()
            kind = str(artifact.get("kind") or "unknown").strip()
            preview = str(artifact.get("preview") or "").strip()
            row = f"{label} [{kind}]"
            if preview:
                row = f"{row}: {preview[:180]}"
            rows.append(row)
        return "Artifacts: " + "; ".join(rows) if rows else "No artifacts attached."
