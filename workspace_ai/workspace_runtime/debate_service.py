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

    def start_debate(
        self,
        *,
        project_id: str,
        topic: str,
        bottlenecks: str = "",
        files: List[str] | None = None,
        participants: List[Dict[str, Any]] | None = None,
        judge_provider: str | None = None,
    ) -> Dict[str, Any]:
        active_participants = participants or [
            {"provider": "openai", "model": self.settings_service.get().get("selected_model", "gpt-5.4")},
            {"provider": "xai", "model": self.settings_service.get().get("selected_model", "gpt-5.4")},
        ]
        debate = self.store.create_debate(
            project_id=project_id,
            topic=topic,
            bottlenecks=bottlenecks,
            files=files or [],
            participants=active_participants,
            judge_provider=(judge_provider or "openai").strip().lower(),
        )
        return self.run_debate(debate_id=str(debate["debate_id"]))

    def run_debate(self, *, debate_id: str) -> Dict[str, Any]:
        debate = self.store.get_debate(debate_id)
        if debate is None:
            return {"status": "not_found", "debate_id": debate_id}
        history: List[Dict[str, str]] = []
        for round_index in range(1, self.max_rounds + 1):
            for participant in debate["participants"]:
                provider_name = str(participant.get("provider") or "openai").strip().lower()
                selected_model = str(participant.get("model") or self.settings_service.get().get("selected_model") or "").strip() or None
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
                self.store.add_debate_round(
                    debate_id=debate_id,
                    round_index=round_index,
                    participant_provider=provider_name,
                    participant_model=str(response.get("model") or selected_model or ""),
                    response=response,
                )
                content = str(response.get("content") or "").strip()
                history.append({"role": "assistant", "content": content})
                if "AGREED" in content.upper():
                    final = self._judge_summary(debate=debate, history=history)
                    finalized = self.store.finalize_debate(debate_id=debate_id, final_plan=final, status="completed")
                    return {"status": "ok", "debate": finalized}
        final = self._judge_summary(debate=debate, history=history)
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
        return (
            f"Round {round_index} debate.\n"
            f"Topic: {debate.get('topic', '')}\n"
            f"Bottlenecks: {str(debate.get('bottlenecks') or '').strip() or '[none]'}\n"
            f"Recent positions:\n{prior or '[none]'}\n\n"
            "Provide a concise engineering recommendation. If you believe the group has converged, end with AGREED."
        )

    def _judge_summary(self, *, debate: Dict[str, Any], history: List[Dict[str, str]]) -> Dict[str, Any]:
        judge_provider = str(debate.get("judge_provider") or "openai").strip().lower()
        selected_model = str(self.settings_service.get().get("selected_model") or "").strip() or None
        api_key = self.settings_service.api_key(judge_provider)
        provider = get_provider(judge_provider, api_key=api_key, model=selected_model)
        chat = ChatService(provider=provider)
        response = chat.respond(
            project_id=str(debate.get("project_id") or "forge"),
            prompt=(
                f"Summarize the final engineering plan for this debate topic: {debate.get('topic', '')}. "
                "Return a concise plan with rationale."
            ),
            context={"memory_context": {"summary": self._debate_context_summary(debate)}, "checkpoints": []},
            history=history,
            model=selected_model,
            api_key=api_key,
            provider_name=judge_provider,
        )
        return {
            "provider": response.get("provider", judge_provider),
            "model": response.get("model", selected_model),
            "content": response.get("content", ""),
            "usage": response.get("usage", {}),
        }
