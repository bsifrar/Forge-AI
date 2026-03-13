from __future__ import annotations

from typing import Any, Dict, Iterable, List

from workspace_ai.providers.base import LLMProvider
from workspace_ai.providers.openai_provider import OpenAIProvider


class ChatService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or OpenAIProvider()

    def _system_prompt(self, *, project_id: str, context: Dict[str, Any]) -> str:
        summary = str(context.get("memory_context", {}).get("summary") or "").strip()
        checkpoints = context.get("checkpoints", [])
        checkpoint_text = "\n".join(
            f"- {str(item.get('summary') or '').strip()}"
            for item in checkpoints[:3]
            if str(item.get("summary") or "").strip()
        )
        return (
            "You are Forge, a persistent AI engineering workspace assistant. Continue the current project conversation, "
            "use provided context, preserve continuity, and stay concise.\n\n"
            f"Active project: {project_id}\n\n"
            f"Retrieved memory context:\n{summary or '[none]'}\n\n"
            f"Recent checkpoints:\n{checkpoint_text or '[none]'}"
        )

    def respond(self, *, project_id: str, prompt: str, context: Dict[str, Any], history: List[Dict[str, Any]], model: str | None = None, api_key: str | None = None) -> Dict[str, Any]:
        conversation = [{"role": str(item.get("role") or "user"), "content": str(item.get("content") or "").strip()} for item in history[-12:] if str(item.get("content") or "").strip()]
        return self.provider.generate(system_prompt=self._system_prompt(project_id=project_id, context=context), user_prompt=prompt, conversation=conversation, model=model, api_key=api_key)

    def respond_stream(self, *, project_id: str, prompt: str, context: Dict[str, Any], history: List[Dict[str, Any]], model: str | None = None, api_key: str | None = None) -> Iterable[Dict[str, Any]]:
        conversation = [{"role": str(item.get("role") or "user"), "content": str(item.get("content") or "").strip()} for item in history[-12:] if str(item.get("content") or "").strip()]
        return self.provider.generate_stream(system_prompt=self._system_prompt(project_id=project_id, context=context), user_prompt=prompt, conversation=conversation, model=model, api_key=api_key)
