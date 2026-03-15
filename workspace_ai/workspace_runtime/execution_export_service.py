from __future__ import annotations

from typing import Any, Dict, List

from workspace_ai.workspace_memory.session_store import SessionStore


_DIVIDER_HEAVY = "═" * 51
_DIVIDER_LIGHT = "─" * 51


class ExecutionExportService:
    def __init__(self, *, store: SessionStore) -> None:
        self.store = store

    def export_execution(self, *, execution_id: str) -> Dict[str, Any]:
        execution = self.store.get_execution(execution_id)
        if execution is None:
            return {"status": "not_found", "execution_id": execution_id}
        text = self._build_text(execution)
        return {
            "status": "ok",
            "execution_id": execution_id,
            "export": {
                "text": text,
                "char_count": len(text),
                "line_count": text.count("\n") + 1,
            },
        }

    # ── text builder ──────────────────────────────────────────────────────────

    def _build_text(self, execution: Dict[str, Any]) -> str:
        lines: List[str] = []
        proposal = execution.get("proposal") if isinstance(execution.get("proposal"), dict) else {}
        result = execution.get("execution") if isinstance(execution.get("execution"), dict) else {}
        source_plan = execution.get("source_plan") if isinstance(execution.get("source_plan"), dict) else {}

        lines.append(_DIVIDER_HEAVY)
        lines.append("FORGE EXECUTION EXPORT")
        lines.append(_DIVIDER_HEAVY)
        lines.append("")

        # Metadata block
        mode = str(proposal.get("mode") or result.get("mode") or "read_only_v1")
        context_source = str(proposal.get("context_source") or "unknown")
        import_count = len(execution.get("context_import_ids") or [])
        debate_id = str(execution.get("debate_id") or "")
        source_type = str(source_plan.get("source_type") or "")

        lines.append(f"Execution ID : {execution.get('execution_id', '')}")
        lines.append(f"Project      : {execution.get('project_id', '')}")
        if debate_id:
            suffix = f" · source type: {source_type}" if source_type else ""
            lines.append(f"Debate ID    : {debate_id}{suffix}")
        lines.append(f"Status       : {execution.get('status', 'unknown')}")
        lines.append(f"Mode         : {mode}")
        lines.append(f"Context      : {context_source} ({import_count} import(s))")
        lines.append(f"Created      : {execution.get('created_at', '')}")
        if str(execution.get("approval_note") or "").strip():
            lines.append(f"Approval note: {execution['approval_note']}")
        lines.append("")

        # Source plan
        plan_content = str(source_plan.get("content") or "").strip()
        topic = str(source_plan.get("topic") or "").strip()
        if plan_content or topic:
            lines.extend(self._sec("SOURCE PLAN"))
            if topic:
                lines.append(f"Topic: {topic}")
                lines.append("")
            if plan_content:
                lines.append("Plan:")
                for plan_line in plan_content.splitlines():
                    lines.append(f"  {plan_line}")
            lines.append("")

        # Context note
        imported_context = str(proposal.get("imported_context") or "").strip()
        if imported_context:
            lines.extend(self._sec("IMPORTED CONTEXT"))
            for ctx_line in imported_context.splitlines():
                lines.append(f"  {ctx_line}")
            lines.append("")

        # Proposed steps
        steps = proposal.get("steps") if isinstance(proposal.get("steps"), list) else []
        if steps:
            lines.extend(self._sec("PROPOSED STEPS"))
            for step in steps:
                if not isinstance(step, dict):
                    continue
                lines.append(f"Step {step.get('step', '?')} · {step.get('status', 'pending')}")
                summary = str(step.get("summary") or "").strip()
                if summary:
                    lines.append(f"  {summary}")
                lines.append("")

        # Suggested commands (change_plan mode)
        commands = result.get("commands") if isinstance(result.get("commands"), list) else proposal.get("commands") if isinstance(proposal.get("commands"), list) else []
        if commands:
            lines.extend(self._sec("SUGGESTED COMMANDS"))
            for cmd in commands:
                lines.append(f"  {cmd}")
            lines.append("")

        # Patch plan (change_plan mode)
        patch_plan = result.get("patch_plan") if isinstance(result.get("patch_plan"), dict) else proposal.get("patch_plan") if isinstance(proposal.get("patch_plan"), dict) else None
        if patch_plan:
            lines.extend(self._sec("PATCH PLAN"))
            lines.append(f"Format  : {patch_plan.get('format', 'unknown')}")
            targets = patch_plan.get("targets") if isinstance(patch_plan.get("targets"), list) else []
            if targets:
                lines.append("Targets :")
                for t in targets:
                    lines.append(f"  {t}")
            hunks = patch_plan.get("hunks") if isinstance(patch_plan.get("hunks"), list) else []
            if hunks:
                lines.append("Hunks   :")
                for hunk in hunks:
                    if not isinstance(hunk, dict):
                        continue
                    hunk_target = str(hunk.get("target") or "").strip()
                    hunk_reason = str(hunk.get("reason") or hunk.get("change_summary") or "").strip()
                    lines.append(f"  [{hunk_target}] {hunk_reason}")
            lines.append("")

        # Patch draft (change_plan mode)
        patch_draft = str(result.get("patch_draft") or proposal.get("patch_draft") or "").strip()
        if patch_draft:
            lines.extend(self._sec("PATCH DRAFT"))
            lines.append(patch_draft)
            lines.append("")

        lines.append(_DIVIDER_HEAVY)
        lines.append("END FORGE EXECUTION EXPORT")
        lines.append(_DIVIDER_HEAVY)
        return "\n".join(lines)

    @staticmethod
    def _sec(title: str) -> List[str]:
        return [_DIVIDER_LIGHT, title, _DIVIDER_LIGHT, ""]
