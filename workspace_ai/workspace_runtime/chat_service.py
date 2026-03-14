from __future__ import annotations

from typing import Any, Dict, Iterable, List

from workspace_ai.providers import get_provider
from workspace_ai.providers.base import LLMProvider


class ChatService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider

    def _system_prompt(self, *, project_id: str, context: Dict[str, Any]) -> str:
        summary = str(context.get("memory_context", {}).get("summary") or "").strip()
        checkpoints = context.get("checkpoints", [])
        checkpoint_text = "\n".join(
            f"- {str(item.get('summary') or '').strip()}"
            for item in checkpoints[:3]
            if str(item.get("summary") or "").strip()
        )
        preferences = str(context.get("personal_preferences") or "").strip()
        instructions = str(context.get("project_instructions") or "").strip()
        imported = str(context.get("imported_context") or "").strip()
        pref_section = f"\nUser preferences:\n{preferences}" if preferences else ""
        instr_section = f"\nProject instructions:\n{instructions}" if instructions else ""
        import_section = f"\n\n{imported}" if imported else ""
        return (
            "You are Forge, a persistent AI engineering workspace assistant. Continue the current project conversation, "
            "use provided context, preserve continuity, and stay concise.\n\n"
            f"Active project: {project_id}\n\n"
            f"Retrieved memory context:\n{summary or '[none]'}\n\n"
            f"Recent checkpoints:\n{checkpoint_text or '[none]'}"
            f"{pref_section}"
            f"{instr_section}"
            f"{import_section}"
        )

    def _provider(self, provider_name: str, *, api_key: str | None = None, model: str | None = None) -> LLMProvider:
        if self.provider is not None:
            return self.provider
        return get_provider(provider_name, api_key=api_key, model=model)

    def respond(self, *, project_id: str, prompt: str, context: Dict[str, Any], history: List[Dict[str, Any]], model: str | None = None, api_key: str | None = None, provider_name: str = "openai") -> Dict[str, Any]:
        conversation = [{"role": str(item.get("role") or "user"), "content": str(item.get("content") or "").strip()} for item in history[-12:] if str(item.get("content") or "").strip()]
        provider = self._provider(provider_name, api_key=api_key, model=model)
        return provider.generate(system_prompt=self._system_prompt(project_id=project_id, context=context), user_prompt=prompt, conversation=conversation, model=model, api_key=api_key)

    def respond_stream(self, *, project_id: str, prompt: str, context: Dict[str, Any], history: List[Dict[str, Any]], model: str | None = None, api_key: str | None = None, provider_name: str = "openai") -> Iterable[Dict[str, Any]]:
        conversation = [{"role": str(item.get("role") or "user"), "content": str(item.get("content") or "").strip()} for item in history[-12:] if str(item.get("content") or "").strip()]
        provider = self._provider(provider_name, api_key=api_key, model=model)
        return provider.generate_stream(system_prompt=self._system_prompt(project_id=project_id, context=context), user_prompt=prompt, conversation=conversation, model=model, api_key=api_key)
