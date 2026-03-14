from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.context_import_service import ContextImportService
from workspace_ai.workspace_runtime.settings_service import SettingsService


class HandoffService:
    def __init__(
        self,
        *,
        store: SessionStore | None = None,
        settings_service: SettingsService | None = None,
    ) -> None:
        self.store = store or SessionStore()
        self.settings_service = settings_service or SettingsService(store=self.store)
        self.context_import_service = ContextImportService(store=self.store)

    # ── public entry points ───────────────────────────────────────────────────

    def build_from_debate(self, *, debate_id: str) -> Dict[str, Any]:
        debate = self.store.get_debate(debate_id)
        if debate is None:
            return {"status": "not_found", "debate_id": debate_id}
        return {"status": "ok", "handoff": self._assemble_debate_handoff(debate=debate)}

    def build_from_execution(self, *, execution_id: str) -> Dict[str, Any]:
        execution = self.store.get_execution(execution_id)
        if execution is None:
            return {"status": "not_found", "execution_id": execution_id}
        debate_id = str(execution.get("debate_id") or "").strip()
        debate = self.store.get_debate(debate_id) if debate_id else None
        return {"status": "ok", "handoff": self._assemble_execution_handoff(execution=execution, debate=debate)}

    # ── assembly ──────────────────────────────────────────────────────────────

    def _settings_layer(self) -> Dict[str, str]:
        s = self.settings_service.get()
        return {
            "personal_preferences": str(s.get("personal_preferences") or "").strip(),
            "project_instructions": str(s.get("project_instructions") or "").strip(),
        }

    def _resolve_imported_context(self, *, project_id: str, import_ids: List[str]) -> str:
        if import_ids:
            return self.context_import_service.build_context_block_for_ids(
                project_id=project_id, import_ids=import_ids
            )
        return self.context_import_service.build_context_block(project_id=project_id)

    def _final_plan_content(self, final_plan: Dict[str, Any]) -> str:
        # final_plan may have 'content' (raw) or 'plan' (judge structured) or 'structured.plan'
        if isinstance(final_plan, dict):
            for key in ("content", "plan"):
                value = str(final_plan.get(key) or "").strip()
                if value:
                    return value
            structured = final_plan.get("structured")
            if isinstance(structured, dict):
                value = str(structured.get("plan") or "").strip()
                if value:
                    return value
        return ""

    def _assemble_debate_handoff(self, *, debate: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(debate.get("project_id") or "")
        import_ids: List[str] = debate.get("context_import_ids") if isinstance(debate.get("context_import_ids"), list) else []
        settings = self._settings_layer()
        imported_context = self._resolve_imported_context(project_id=project_id, import_ids=import_ids)
        artifacts = debate.get("files") if isinstance(debate.get("files"), list) else []
        final_plan = debate.get("final_plan") if isinstance(debate.get("final_plan"), dict) else {}
        plan_content = self._final_plan_content(final_plan)
        handoff = {
            "debate_id": str(debate.get("debate_id") or ""),
            "execution_id": None,
            "project_id": project_id,
            "debate_style": str(debate.get("debate_style") or "standard"),
            "topic": str(debate.get("topic") or ""),
            "personal_preferences": settings["personal_preferences"],
            "project_instructions": settings["project_instructions"],
            "active_context_import_ids": import_ids,
            "imported_context": imported_context,
            "artifacts": artifacts,
            "final_plan": plan_content,
            "execution_mode": None,
            "suggested_commands": None,
            "patch_draft": None,
            "recommended_next_action": self._debate_next_action(debate=debate, plan_content=plan_content),
        }
        handoff["text"] = self._render_text(handoff)
        return handoff

    def _assemble_execution_handoff(self, *, execution: Dict[str, Any], debate: Dict[str, Any] | None) -> Dict[str, Any]:
        project_id = str(execution.get("project_id") or "")
        proposal = execution.get("proposal") if isinstance(execution.get("proposal"), dict) else {}
        source_plan = execution.get("source_plan") if isinstance(execution.get("source_plan"), dict) else {}
        import_ids: List[str] = execution.get("context_import_ids") if isinstance(execution.get("context_import_ids"), list) else []
        settings = self._settings_layer()

        # imported_context: prefer the baked-in proposal field (exact state at creation time)
        imported_context = str(proposal.get("imported_context") or "").strip()
        if not imported_context:
            imported_context = self._resolve_imported_context(project_id=project_id, import_ids=import_ids)

        artifacts = []
        source_artifacts = proposal.get("source") if isinstance(proposal.get("source"), dict) else {}
        if isinstance(source_artifacts.get("artifacts"), list):
            artifacts = source_artifacts["artifacts"]
        elif isinstance(source_plan.get("artifacts"), list):
            artifacts = source_plan["artifacts"]

        plan_content = str(source_plan.get("content") or "").strip()
        execution_mode = str(proposal.get("mode") or "read_only_v1")
        commands: List[str] | None = proposal.get("commands") if isinstance(proposal.get("commands"), list) else None
        patch_draft = str(proposal.get("patch_draft") or "").strip() or None

        debate_style = "standard"
        topic = str(source_plan.get("topic") or "")
        if debate is not None:
            debate_style = str(debate.get("debate_style") or "standard")
            topic = topic or str(debate.get("topic") or "")

        handoff = {
            "debate_id": str(execution.get("debate_id") or "") or None,
            "execution_id": str(execution.get("execution_id") or ""),
            "project_id": project_id,
            "debate_style": debate_style,
            "topic": topic,
            "personal_preferences": settings["personal_preferences"],
            "project_instructions": settings["project_instructions"],
            "active_context_import_ids": import_ids,
            "imported_context": imported_context,
            "artifacts": artifacts,
            "final_plan": plan_content,
            "execution_mode": execution_mode,
            "suggested_commands": commands,
            "patch_draft": patch_draft,
            "recommended_next_action": self._execution_next_action(execution=execution, execution_mode=execution_mode),
        }
        handoff["text"] = self._render_text(handoff)
        return handoff

    # ── recommended next action ───────────────────────────────────────────────

    def _debate_next_action(self, *, debate: Dict[str, Any], plan_content: str) -> str:
        status = str(debate.get("status") or "")
        if status in ("completed", "max_rounds") and plan_content:
            return "The debate has converged. Copy this package to your implementation model to begin execution."
        if status == "failed":
            return "The debate failed to produce a plan. Review provider errors before proceeding."
        return "The debate is incomplete. Wait for it to finish before handing off."

    def _execution_next_action(self, *, execution: Dict[str, Any], execution_mode: str) -> str:
        status = str(execution.get("status") or "")
        if status == "pending_approval":
            return "Review the proposed execution plan and approve or reject it in Forge before handing off."
        if status == "rejected":
            return "Execution was rejected. Revise the plan or start a new debate."
        if execution_mode == "change_plan_v1":
            return (
                "Execution was approved as a change plan. Apply the suggested commands and patch draft "
                "in the order shown. Verify with the test suite after each change."
            )
        return (
            "Execution was approved (read-only). Use the steps and artifacts below as a manual implementation guide."
        )

    # ── text renderer ─────────────────────────────────────────────────────────

    def _render_text(self, h: Dict[str, Any]) -> str:
        lines: List[str] = []
        _h = "=" * 60
        _s = "-" * 40

        lines.append(_h)
        lines.append("FORGE HANDOFF PACKAGE")
        lines.append(_h)
        lines.append(f"Generated : {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        lines.append(f"Project   : {h['project_id']}")
        if h.get("debate_id"):
            lines.append(f"Debate    : {h['debate_id']}")
        if h.get("execution_id"):
            lines.append(f"Execution : {h['execution_id']}")
        lines.append(f"Style     : {h['debate_style']}")
        if h.get("execution_mode"):
            lines.append(f"Exec mode : {h['execution_mode']}")
        lines.append("")

        lines.append(_s)
        lines.append("TOPIC")
        lines.append(_s)
        lines.append(h.get("topic") or "[none]")
        lines.append("")

        lines.append(_s)
        lines.append("FINAL PLAN")
        lines.append(_s)
        lines.append(h.get("final_plan") or "[not yet available]")
        lines.append("")

        artifacts = h.get("artifacts") or []
        if artifacts:
            lines.append(_s)
            lines.append("ARTIFACTS")
            lines.append(_s)
            for art in artifacts:
                label = str(art.get("label") or art.get("path") or "artifact")
                kind = str(art.get("kind") or "")
                size = int(art.get("size_bytes") or 0)
                size_str = f", {size:,} B" if size else ""
                lines.append(f"  {label}" + (f"  [{kind}{size_str}]" if kind else ""))
            lines.append("")

        imported = str(h.get("imported_context") or "").strip()
        if imported:
            lines.append(_s)
            lines.append("IMPORTED CONTEXT")
            lines.append(_s)
            lines.append(imported)
            lines.append("")

        prefs = str(h.get("personal_preferences") or "").strip()
        instr = str(h.get("project_instructions") or "").strip()
        if prefs or instr:
            lines.append(_s)
            lines.append("PREFERENCES & INSTRUCTIONS")
            lines.append(_s)
            if prefs:
                lines.append(f"Preferences: {prefs}")
            if instr:
                lines.append(f"Instructions: {instr}")
            lines.append("")

        commands = h.get("suggested_commands")
        if commands:
            lines.append(_s)
            lines.append("SUGGESTED COMMANDS")
            lines.append(_s)
            for cmd in commands:
                lines.append(f"  {cmd}")
            lines.append("")

        patch_draft = h.get("patch_draft")
        if patch_draft:
            lines.append(_s)
            lines.append("PATCH DRAFT")
            lines.append(_s)
            lines.append(patch_draft)
            lines.append("")

        lines.append(_s)
        lines.append("RECOMMENDED NEXT ACTION")
        lines.append(_s)
        lines.append(h.get("recommended_next_action") or "")
        lines.append("")

        return "\n".join(lines)
