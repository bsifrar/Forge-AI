from workspace_ai.providers.base import LLMProvider
from workspace_ai.providers.anthropic_provider import AnthropicProvider
from workspace_ai.providers.openai_provider import OpenAIProvider
from workspace_ai.providers.xai_provider import XAIProvider


def get_provider(provider_name: str, *, api_key: str | None = None, model: str | None = None) -> LLMProvider:
    normalized = provider_name.strip().lower()
    if normalized == "openai":
        return OpenAIProvider(api_key=api_key, model=model)
    if normalized == "xai":
        return XAIProvider(api_key=api_key, model=model)
    if normalized == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model)
    raise ValueError(f"Unsupported provider: {provider_name}")


__all__ = ["LLMProvider", "AnthropicProvider", "OpenAIProvider", "XAIProvider", "get_provider"]
