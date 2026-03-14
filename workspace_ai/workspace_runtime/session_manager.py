from __future__ import annotations

import json
from typing import Any, Dict, Iterable

from workspace_ai.adapters.base import MemoryAdapter
from workspace_ai.workspace_import.chatgpt_importer import ChatGPTExportImporter
from workspace_ai.workspace_memory.context_service import ContextService
from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.chat_service import ChatService
from workspace_ai.workspace_runtime.context_import_service import ContextImportService
from workspace_ai.workspace_runtime.debate_service import DebateService
from workspace_ai.workspace_runtime.executor_service import ExecutorService
from workspace_ai.workspace_runtime.handoff_service import HandoffService
from workspace_ai.workspace_runtime.policy_service import PolicyService
from workspace_ai.workspace_runtime.settings_service import SettingsService
from workspace_ai.workspace_runtime.stream_manager import StreamManager


class SessionManager:
    def __init__(self, *, adapter: MemoryAdapter, store: SessionStore | None = None) -> None:
        self.store = store or SessionStore()
        self.adapter = adapter
        self.context_service = ContextService(adapter=adapter, store=self.store)
        self.chat_service = ChatService()
        self.stream_manager = StreamManager()
        self.settings_service = SettingsService(store=self.store)
        self.debate_service = DebateService(store=self.store, settings_service=self.settings_service)
        self.context_import_service = ContextImportService(store=self.store)
        self.executor_service = ExecutorService(store=self.store)
        self.handoff_service = HandoffService(store=self.store, settings_service=self.settings_service)
        self.policy_service = PolicyService(store=self.store, settings_service=self.settings_service)
        self.importer = ChatGPTExportImporter(store=self.store, adapter=self.adapter)

    def status(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "component": "workspace_ai",
            "session_count": len(self.store.list_sessions(limit=500)),
            "adapter": self.context_service.adapter_health(),
        }

    def settings(self) -> Dict[str, Any]:
        return {"status": "ok", "settings": self.settings_service.get()}

    def _chat_role(self) -> Dict[str, str]:
        return self.settings_service.model_role("chat")

    def _inject_preferences(self, context: Dict[str, Any], *, project_id: str = "") -> Dict[str, Any]:
        s = self.settings_service.get()
        context["personal_preferences"] = str(s.get("personal_preferences") or "").strip()
        context["project_instructions"] = str(s.get("project_instructions") or "").strip()
        if project_id:
            context["imported_context"] = self.context_import_service.build_context_block(project_id=project_id)
        else:
            context["imported_context"] = ""
        return context

    def context_preview(self, *, project_id: str, context_import_ids: list[str] | None = None) -> Dict[str, Any]:
        s = self.settings_service.get()
        chat_role = self._chat_role()
        if context_import_ids:
            imported_block = self.context_import_service.build_context_block_for_ids(project_id=project_id, import_ids=context_import_ids)
            active_import_ids = list(context_import_ids)
        else:
            imported_block = self.context_import_service.build_context_block(project_id=project_id)
            active_import_ids = [item["import_id"] for item in self.store.list_enabled_context_imports(project_id=project_id)]
        stub_context = {
            "memory_context": {"summary": "[retrieved memory would appear here]"},
            "checkpoints": [],
            "personal_preferences": str(s.get("personal_preferences") or "").strip(),
            "project_instructions": str(s.get("project_instructions") or "").strip(),
            "imported_context": imported_block,
        }
        system_prompt = self.chat_service._system_prompt(project_id=project_id, context=stub_context)
        return {
            "status": "ok",
            "project_id": project_id,
            "chat_role": chat_role,
            "debate_style": s.get("debate_style", "standard"),
            "personal_preferences": stub_context["personal_preferences"],
            "project_instructions": stub_context["project_instructions"],
            "imported_context_count": len(active_import_ids),
            "active_import_ids": active_import_ids,
            "system_prompt": system_prompt,
        }

    def adapter_status(self) -> Dict[str, Any]:
        return {"status": "ok", "adapter": self.context_service.adapter_health()}

    def list_debates(self, *, project_id: str | None = None, limit: int = 50) -> Dict[str, Any]:
        return self.debate_service.list_debates(project_id=project_id, limit=limit)

    def get_debate(self, *, debate_id: str) -> Dict[str, Any]:
        return self.debate_service.get_debate(debate_id=debate_id)

    def list_executions(self, *, project_id: str | None = None, limit: int = 50) -> Dict[str, Any]:
        return self.executor_service.list_executions(project_id=project_id, limit=limit)

    def get_execution(self, *, execution_id: str) -> Dict[str, Any]:
        return self.executor_service.get_execution(execution_id=execution_id)

    def create_execution(self, *, project_id: str, debate_id: str | None = None, plan: str = "", execution_mode: str = "read_only_v1", context_import_ids: list[str] | None = None) -> Dict[str, Any]:
        result = self.executor_service.create_execution(
            project_id=project_id,
            debate_id=debate_id,
            plan=plan,
            execution_mode=execution_mode,
            context_import_ids=context_import_ids or None,
        )
        execution = result.get("execution")
        if isinstance(execution, dict):
            self.stream_manager.publish(
                event_type="workspace.execution.created",
                session_id=None,
                payload={"execution": execution},
            )
        return result

    def decide_execution(self, *, execution_id: str, approved: bool, note: str = "") -> Dict[str, Any]:
        result = self.executor_service.decide_execution(execution_id=execution_id, approved=approved, note=note)
        execution = result.get("execution")
        if isinstance(execution, dict):
            self.stream_manager.publish(
                event_type="workspace.execution.updated",
                session_id=None,
                payload={"execution": execution},
            )
        return result

    def start_debate(
        self,
        *,
        project_id: str,
        topic: str,
        bottlenecks: str = "",
        files: list[str] | None = None,
        participants: list[Dict[str, Any]] | None = None,
        max_rounds: int = 5,
        judge_provider: str | None = None,
        debate_style: str | None = None,
        context_import_ids: list[str] | None = None,
    ) -> Dict[str, Any]:
        result = self.debate_service.start_debate(
            project_id=project_id,
            topic=topic,
            bottlenecks=bottlenecks,
            files=files,
            participants=participants,
            max_rounds=max_rounds,
            judge_provider=judge_provider,
            debate_style=debate_style,
            context_import_ids=context_import_ids or None,
        )
        debate = result.get("debate")
        if isinstance(debate, dict):
            self.stream_manager.publish(
                event_type="workspace.debate.completed",
                session_id=None,
                payload={"debate": debate},
            )
        return result

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "settings": self.settings_service.update(updates)}

    def bootstrap_local_setup(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "settings": self.settings_service.bootstrap_local_setup(updates)}

    def create_session(self, *, project_id: str, title: str, mode: str) -> Dict[str, Any]:
        session = self.store.create_session(project_id=project_id, title=title, mode=mode)
        self.stream_manager.publish(event_type="workspace.session.created", session_id=session["session_id"], payload=session)
        return {"status": "ok", "session": session}

    def list_sessions(self, *, project_id: str | None = None, limit: int = 50) -> Dict[str, Any]:
        rows = self.store.list_sessions(project_id=project_id, limit=limit)
        return {"status": "ok", "count": len(rows), "sessions": rows}

    def list_imports(self, *, project_id: str | None = None, limit: int = 50) -> Dict[str, Any]:
        rows = self.store.list_imported_sessions(project_id=project_id, limit=limit)
        return {"status": "ok", "count": len(rows), "sessions": rows}

    # ── context imports ───────────────────────────────────────────────────────

    def create_context_import(self, *, project_id: str, source_label: str, content: str, category: str) -> Dict[str, Any]:
        try:
            item = self.context_import_service.create(project_id=project_id, source_label=source_label, content=content, category=category)
            return {"status": "ok", "import": item}
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    def list_context_imports(self, *, project_id: str | None = None, limit: int = 200) -> Dict[str, Any]:
        return self.context_import_service.list_imports(project_id=project_id, limit=limit)

    def set_context_import_enabled(self, *, import_id: str, enabled: bool) -> Dict[str, Any]:
        return self.context_import_service.set_enabled(import_id=import_id, enabled=enabled)

    def delete_context_import(self, *, import_id: str) -> Dict[str, Any]:
        return self.context_import_service.delete(import_id=import_id)

    # ── handoff ───────────────────────────────────────────────────────────────

    def build_handoff(self, *, debate_id: str | None = None, execution_id: str | None = None) -> Dict[str, Any]:
        if execution_id:
            return self.handoff_service.build_from_execution(execution_id=execution_id)
        if debate_id:
            return self.handoff_service.build_from_debate(debate_id=debate_id)
        return {"status": "error", "detail": "debate_id or execution_id required"}

    def search_sessions(self, *, query: str, project_id: str | None = None, limit: int = 25) -> Dict[str, Any]:
        rows = self.store.search_sessions(query=query, project_id=project_id, limit=limit)
        return {"status": "ok", "query": query, "count": len(rows), "sessions": rows}

    def get_session(self, session_id: str) -> Dict[str, Any] | None:
        session = self.store.get_session(session_id)
        if session is None:
            return None
        return {"status": "ok", "session": session, "recent_checkpoint": next(iter(self.store.list_checkpoints(session_id=session_id, limit=1)), None)}

    def list_messages(self, *, session_id: str, limit: int = 200) -> Dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            return {"status": "not_found", "session_id": session_id}
        rows = self.store.list_messages(session_id=session_id, limit=limit)
        return {"status": "ok", "session": session, "count": len(rows), "messages": rows}

    def clone_session(self, *, session_id: str, title: str | None = None, include_messages: bool = True) -> Dict[str, Any]:
        source = self.store.get_session(session_id)
        if source is None:
            return {"status": "not_found", "session_id": session_id}
        cloned = self.store.create_session(
            project_id=str(source.get("project_id") or "default"),
            title=(title or f"Branch from {source.get('title') or session_id}").strip(),
            mode=str(source.get("mode") or "chat"),
            source="workspace_branch",
            external_conversation_id=str(source.get("external_conversation_id") or ""),
            external_title=str(source.get("external_title") or ""),
        )
        if include_messages:
            messages = self.store.list_messages(session_id=session_id, limit=1000)
            for message in messages:
                self.store.add_message(
                    session_id=str(cloned["session_id"]),
                    role=str(message.get("role") or "user"),
                    content=str(message.get("content") or ""),
                    provider=str(message.get("provider") or "workspace"),
                    metadata={
                        **(message.get("metadata") if isinstance(message.get("metadata"), dict) else {}),
                        "branched_from_session_id": session_id,
                    },
                )
        checkpoint = self.store.create_checkpoint(
            session_id=str(cloned["session_id"]),
            summary=f"Branched from session {session_id}",
            state={"branched_from_session_id": session_id, "source_title": source.get("title", "")},
        )
        return {"status": "ok", "session": cloned, "checkpoint": checkpoint}

    def update_session_status(self, *, session_id: str, status: str) -> Dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            return {"status": "not_found", "session_id": session_id}
        updated = self.store.update_session_status(session_id=session_id, status=status)
        if updated is None:
            return {"status": "not_found", "session_id": session_id}
        self.stream_manager.publish(event_type="workspace.session.updated", session_id=session_id, payload=updated)
        return {"status": "ok", "session": updated}

    def delete_session(self, *, session_id: str) -> Dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            return {"status": "not_found", "session_id": session_id}
        deleted = self.store.delete_session(session_id=session_id)
        if not deleted:
            return {"status": "not_found", "session_id": session_id}
        self.stream_manager.publish(event_type="workspace.session.deleted", session_id=session_id, payload={"session_id": session_id})
        return {"status": "ok", "deleted_session_id": session_id, "session": session}

    def resume_imported_session(self, *, query: str, project_id: str | None = None) -> Dict[str, Any]:
        matches = [row for row in self.store.search_sessions(query=query, project_id=project_id, limit=10) if row.get("source") == "chatgpt_export"]
        if not matches:
            return {"status": "not_found", "query": query, "project_id": project_id}
        return {"status": "ok", "matched_session": matches[0]}

    def import_chatgpt_export(self, *, export_path: str, project_id: str, conversation_ids: list[str] | None = None, max_conversations: int = 25) -> Dict[str, Any]:
        return self.importer.import_export(export_path=export_path, project_id=project_id, conversation_ids=conversation_ids, max_conversations=max_conversations)

    def import_chatgpt_file(self, *, file_bytes: bytes, filename: str, project_id: str, conversation_ids: list[str] | None = None, max_conversations: int = 25) -> Dict[str, Any]:
        try:
            payload = json.loads(file_bytes.decode("utf-8"))
        except Exception as exc:
            return {"status": "invalid", "reason": f"could not parse JSON: {exc}", "filename": filename}
        return self.importer.import_export_payload(
            payload=payload,
            project_id=project_id,
            conversation_ids=conversation_ids,
            max_conversations=max_conversations,
            export_path=filename,
        )

    def add_message(self, *, session_id: str, content: str, role: str, token_budget: int, model: str | None = None) -> Dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            return {"status": "not_found", "session_id": session_id}
        user_message = self.store.add_message(session_id=session_id, role=role, content=content, provider="workspace")
        self.adapter.ingest_message(project_id=session["project_id"], conversation_id=session.get("external_conversation_id") or session_id, role=role, content=content, title=session["title"], metadata={"workspace_session_id": session_id})
        policy = self.policy_service.allow_live_call()
        context = self._inject_preferences(self.context_service.build_context(project_id=session["project_id"], prompt=content, session_id=session_id, token_budget=token_budget), project_id=session["project_id"])
        history = self.store.list_messages(session_id=session_id, limit=40)
        chat_role = self._chat_role()
        selected_model = model or chat_role["model"]
        selected_provider = chat_role["provider"]
        api_key = self.settings_service.api_key(selected_provider)
        if policy["allowed"]:
            response = self.chat_service.respond(project_id=session["project_id"], prompt=content, context=context, history=history[:-1], model=selected_model, api_key=api_key, provider_name=selected_provider)
            if response.get("mode") == "live":
                self.policy_service.record_live_call(session_id=session_id, provider=str(response.get("provider") or selected_provider), model=str(response.get("model") or selected_model), mode=str(response.get("mode") or "live"), usage=response.get("usage", {}))
        else:
            response = {"content": f"[workspace blocked:{policy['reason']}] {content[:400]}", "provider": selected_provider, "model": selected_model, "mode": "blocked", "usage": {}}
        assistant = self.store.add_message(
            session_id=session_id,
            role="assistant",
            content=str(response.get("content") or "").strip(),
            provider=str(response.get("provider") or "workspace"),
            metadata={"model_response": {"mode": response.get("mode"), "model": response.get("model"), "provider": response.get("provider"), "usage": response.get("usage", {}), "policy_reason": policy["reason"]}, "context_preview": context},
        )
        self.adapter.ingest_message(project_id=session["project_id"], conversation_id=session.get("external_conversation_id") or session_id, role="assistant", content=assistant["content"], title=session["title"], metadata={"workspace_session_id": session_id})
        return {"status": "ok", "session": session, "message": user_message, "assistant_message": assistant, "context": context}

    def stream_message(self, *, session_id: str, content: str, role: str, token_budget: int, model: str | None = None) -> Iterable[Dict[str, Any]]:
        session = self.store.get_session(session_id)
        if session is None:
            yield {"type": "workspace.error", "status": "not_found", "session_id": session_id}
            return
        user_message = self.store.add_message(session_id=session_id, role=role, content=content, provider="workspace")
        yield {"type": "workspace.message.received", "message": user_message}
        self.adapter.ingest_message(project_id=session["project_id"], conversation_id=session.get("external_conversation_id") or session_id, role=role, content=content, title=session["title"], metadata={"workspace_session_id": session_id})
        policy = self.policy_service.allow_live_call()
        context = self._inject_preferences(self.context_service.build_context(project_id=session["project_id"], prompt=content, session_id=session_id, token_budget=token_budget), project_id=session["project_id"])
        history = self.store.list_messages(session_id=session_id, limit=40)
        chat_role = self._chat_role()
        selected_model = model or chat_role["model"]
        selected_provider = chat_role["provider"]
        api_key = self.settings_service.api_key(selected_provider)
        collected: list[str] = []
        meta: Dict[str, Any] = {"mode": "blocked", "model": selected_model, "provider": selected_provider, "usage": {}, "policy_reason": policy["reason"]}
        if policy["allowed"]:
            for event in self.chat_service.respond_stream(project_id=session["project_id"], prompt=content, context=context, history=history[:-1], model=selected_model, api_key=api_key, provider_name=selected_provider):
                event_type = str(event.get("type") or "")
                if event_type == "response.output_text.delta":
                    delta = str(event.get("delta") or "")
                    collected.append(delta)
                    yield {"type": "workspace.response.delta", "delta": delta}
                elif event_type == "response.completed":
                    response = event.get("response", {}) if isinstance(event.get("response"), dict) else {}
                    source = response if response else event
                    meta = {"mode": response.get("mode"), "model": response.get("model"), "provider": response.get("provider"), "usage": response.get("usage", {}), "policy_reason": policy["reason"]}
                    meta = {
                        "mode": str(source.get("mode") or "live"),
                        "model": source.get("model"),
                        "provider": str(source.get("provider") or selected_provider),
                        "usage": source.get("usage", {}) if isinstance(source.get("usage"), dict) else {},
                        "policy_reason": policy["reason"],
                    }
                    completed_text = str(source.get("output_text") or "").strip()
                    if completed_text and not "".join(collected).strip():
                        collected.append(completed_text)
        else:
            blocked = f"[workspace blocked:{policy['reason']}] {content[:400]}"
            for token in blocked.split():
                delta = f"{token} "
                collected.append(delta)
                yield {"type": "workspace.response.delta", "delta": delta}
        assistant_text = "".join(collected).strip()
        assistant = self.store.add_message(session_id=session_id, role="assistant", content=assistant_text, provider=str(meta.get("provider") or "workspace"), metadata={"model_response": meta, "context_preview": context})
        if meta.get("mode") == "live":
            self.policy_service.record_live_call(session_id=session_id, provider=str(meta.get("provider") or "openai"), model=str(meta.get("model") or selected_model), mode=str(meta.get("mode") or "live"), usage=meta.get("usage", {}))
        self.adapter.ingest_message(project_id=session["project_id"], conversation_id=session.get("external_conversation_id") or session_id, role="assistant", content=assistant_text, title=session["title"], metadata={"workspace_session_id": session_id})
        yield {"type": "workspace.response.completed", "message": assistant}
