from __future__ import annotations

from typing import Any, Dict, List

from workspace_ai.providers import get_provider
from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.chat_service import ChatService
from workspace_ai.workspace_runtime.settings_service import SettingsService


class DebateService:
    def __init__(self, *, store: SessionStore, settings_service: SettingsService, max_rounds: int = 5) -> None:
        self.store = store
        self.settings_service = settings_service
        self.max_rounds = max(1, int(max_rounds))

    @staticmethod
    def _normalize_provider(value: str | None, *, field_name: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"openai", "xai"}:
            raise ValueError(f"{field_name} must be one of: openai, xai")
        return normalized

    def _normalize_participants(self, participants: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
        if not participants:
            default_model = str(self.settings_service.get().get("selected_model") or "gpt-5.4")
            return [
                {"provider": "openai", "model": default_model},
                {"provider": "xai", "model": default_model},
            ]
        normalized: List[Dict[str, Any]] = []
        for item in participants:
            provider_name = self._normalize_provider(str(item.get("provider") or ""), field_name="participants.provider")
            selected_model = str(item.get("model") or "").strip()
            normalized.append({"provider": provider_name, "model": selected_model or None})
        if not normalized:
            raise ValueError("participants must include at least one provider")
        return normalized

    def start_debate(
        self,
        *,
        project_id: str,
        topic: str,
        bottlenecks: str = "",
        files: List[str] | None = None,
        participants: List[Dict[str, Any]] | None = None,
        max_rounds: int = 5,
        judge_provider: str | None = None,
    ) -> Dict[str, Any]:
        active_participants = self._normalize_participants(participants)
        bounded_rounds = max(1, min(20, int(max_rounds)))
        normalized_judge = self._normalize_provider(judge_provider or "openai", field_name="judge_provider")
        debate = self.store.create_debate(
            project_id=project_id,
            topic=topic,
            bottlenecks=bottlenecks,
            files=[str(item).strip() for item in (files or []) if str(item).strip()],
            participants=active_participants,
            max_rounds=bounded_rounds,
            judge_provider=normalized_judge,
        )
        return self.run_debate(debate_id=str(debate["debate_id"]), max_rounds=int(debate.get("max_rounds") or max_rounds))

    def run_debate(self, *, debate_id: str, max_rounds: int | None = None) -> Dict[str, Any]:
        debate = self.store.get_debate(debate_id)
        if debate is None:
            return {"status": "not_found", "debate_id": debate_id}
        history: List[Dict[str, str]] = []
        successful_responses = 0
        provider_errors: List[str] = []
        effective_max_rounds = max(1, min(20, int(max_rounds if max_rounds is not None else debate.get("max_rounds") or self.max_rounds)))
        for round_index in range(1, effective_max_rounds + 1):
            for participant in debate["participants"]:
                provider_name = str(participant.get("provider") or "openai").strip().lower()
                selected_model = str(participant.get("model") or self.settings_service.get().get("selected_model") or "").strip() or None
                try:
                    api_key = self.settings_service.api_key(provider_name)
                    provider = get_provider(provider_name, api_key=api_key, model=selected_model)
                    chat = ChatService(provider=provider)
                    response = chat.respond(
                        project_id=str(debate.get("project_id") or "forge"),
                        prompt=self._participant_prompt(debate=debate, history=history, round_index=round_index),
                        context={"memory_context": {"summary": self._debate_context_summary(debate)}, "checkpoints": []},
                        history=history,
                        model=selected_model,
                        api_key=api_key,
                        provider_name=provider_name,
                    )
                except Exception as exc:
                    response = {
                        "content": f"[provider_error:{provider_name}] {exc}",
                        "provider": provider_name,
                        "model": selected_model or "",
                        "mode": "error",
                        "usage": {},
                        "error": str(exc),
                    }
                    provider_errors.append(f"{provider_name}: {exc}")
                self.store.add_debate_round(
                    debate_id=debate_id,
                    round_index=round_index,
                    participant_provider=provider_name,
                    participant_model=str(response.get("model") or selected_model or ""),
                    response=response,
                )
                content = str(response.get("content") or "").strip()
                history.append({"role": "assistant", "content": content})
                if str(response.get("mode") or "") != "error":
                    successful_responses += 1
                if "AGREED" in content.upper() and str(response.get("mode") or "") != "error":
                    final = self._judge_summary(debate=debate, history=history)
                    finalized = self.store.finalize_debate(debate_id=debate_id, final_plan=final, status="completed")
                    return {"status": "ok", "debate": finalized}
        if successful_responses == 0:
            final = {
                "provider": "workspace",
                "model": None,
                "mode": "failed",
                "content": "Debate failed because all participant responses errored.",
                "usage": {},
                "errors": provider_errors,
            }
            finalized = self.store.finalize_debate(debate_id=debate_id, final_plan=final, status="failed")
            return {"status": "ok", "debate": finalized}
        final = self._judge_summary(debate=debate, history=history)
        if provider_errors:
            final["warnings"] = provider_errors
        finalized = self.store.finalize_debate(debate_id=debate_id, final_plan=final, status="max_rounds")
        return {"status": "ok", "debate": finalized}

    def get_debate(self, *, debate_id: str) -> Dict[str, Any]:
        debate = self.store.get_debate(debate_id)
        if debate is None:
            return {"status": "not_found", "debate_id": debate_id}
        return {"status": "ok", "debate": debate}

    def list_debates(self, *, project_id: str | None = None, limit: int = 50) -> Dict[str, Any]:
        debates = self.store.list_debates(project_id=project_id, limit=limit)
        return {"status": "ok", "count": len(debates), "debates": debates}

    def _debate_context_summary(self, debate: Dict[str, Any]) -> str:
        files = ", ".join(str(item) for item in debate.get("files", [])) or "[none]"
        bottlenecks = str(debate.get("bottlenecks") or "").strip() or "[none]"
        return f"Debate topic: {debate.get('topic', '')}\nBottlenecks: {bottlenecks}\nFiles: {files}"

    def _participant_prompt(self, *, debate: Dict[str, Any], history: List[Dict[str, str]], round_index: int) -> str:
        prior = "\n".join(f"- {item['content']}" for item in history[-4:] if str(item.get("content") or "").strip())
        files = "\n".join(f"- {item}" for item in debate.get("files", []) if str(item).strip())
        return (
            f"Round {round_index} debate.\n"
            f"Topic: {debate.get('topic', '')}\n"
            f"Bottlenecks:\n- {str(debate.get('bottlenecks') or '').strip() or '[none]'}\n"
            f"Files:\n{files or '- [none]'}\n"
            f"Recent positions:\n{prior or '[none]'}\n\n"
            "Provide a concise engineering recommendation. If you believe the group has converged, end with AGREED."
        )

    def _judge_summary(self, *, debate: Dict[str, Any], history: List[Dict[str, str]]) -> Dict[str, Any]:
        judge_provider = str(debate.get("judge_provider") or "openai").strip().lower()
        selected_model = str(self.settings_service.get().get("selected_model") or "").strip() or None
        try:
            api_key = self.settings_service.api_key(judge_provider)
            provider = get_provider(judge_provider, api_key=api_key, model=selected_model)
            chat = ChatService(provider=provider)
            response = chat.respond(
                project_id=str(debate.get("project_id") or "forge"),
                prompt=(
                    f"Summarize the agreed engineering plan for this debate topic: {debate.get('topic', '')}. "
                    "Extract the final plan from the debate history. Return a concise plan with rationale and avoid inventing new requirements."
                ),
                context={"memory_context": {"summary": self._debate_context_summary(debate)}, "checkpoints": []},
                history=history,
                model=selected_model,
                api_key=api_key,
                provider_name=judge_provider,
            )
        except Exception as exc:
            return {
                "provider": "workspace",
                "model": selected_model,
                "mode": "fallback",
                "content": (
                    "Judge summary unavailable due to provider error. "
                    f"Last response: {history[-1]['content'] if history else '[none]'}"
                ),
                "usage": {},
                "error": str(exc),
            }
        return {
            "provider": response.get("provider", judge_provider),
            "model": response.get("model", selected_model),
            "content": response.get("content", ""),
            "mode": response.get("mode", "live"),
            "usage": response.get("usage", {}),
        }
