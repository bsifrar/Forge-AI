from __future__ import annotations

import pytest

from workspace_ai.providers import get_provider
from workspace_ai.providers.anthropic_provider import AnthropicProvider


def test_mock_generate_when_no_key(isolated_workspace_env):
    provider = AnthropicProvider(api_key="")
    result = provider.generate(system_prompt="sys", user_prompt="hello world")
    assert result["mode"] == "mock"
    assert result["provider"] == "anthropic"
    assert "[mock:anthropic]" in result["content"]
    assert "hello world" in result["content"]


def test_mock_generate_truncates_long_prompt(isolated_workspace_env):
    provider = AnthropicProvider(api_key="")
    long_prompt = "x" * 800
    result = provider.generate(system_prompt="sys", user_prompt=long_prompt)
    assert len(result["content"]) < 450


def test_mock_stream_when_no_key(isolated_workspace_env):
    provider = AnthropicProvider(api_key="")
    events = list(provider.generate_stream(system_prompt="sys", user_prompt="hello stream"))
    delta_events = [e for e in events if e["type"] == "response.output_text.delta"]
    completed_events = [e for e in events if e["type"] == "response.completed"]
    assert delta_events
    assert len(completed_events) == 1
    assert completed_events[0]["response"]["provider"] == "anthropic"
    assert completed_events[0]["response"]["mode"] == "mock"


def test_capabilities(isolated_workspace_env):
    provider = AnthropicProvider(api_key="")
    caps = provider.capabilities()
    assert caps["provider"] == "anthropic"
    assert caps["streaming"] is True
    assert caps["responses_api"] is False


def test_default_model_from_env(isolated_workspace_env, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-override")
    provider = AnthropicProvider(api_key="")
    assert provider.default_model == "claude-test-override"


def test_default_model_fallback(isolated_workspace_env):
    provider = AnthropicProvider(api_key="")
    assert provider.default_model == "claude-sonnet-4-20250514"


def test_model_override_at_init(isolated_workspace_env):
    provider = AnthropicProvider(api_key="", model="claude-custom")
    assert provider.default_model == "claude-custom"


def test_factory_returns_anthropic_provider(isolated_workspace_env):
    provider = get_provider("anthropic", api_key="")
    assert isinstance(provider, AnthropicProvider)


def test_factory_anthropic_case_insensitive(isolated_workspace_env):
    provider = get_provider("Anthropic", api_key="")
    assert isinstance(provider, AnthropicProvider)


def test_factory_still_rejects_unknown(isolated_workspace_env):
    with pytest.raises(ValueError, match="Unsupported provider"):
        get_provider("unknown-llm")


def test_mock_generate_uses_overridden_model(isolated_workspace_env):
    provider = AnthropicProvider(api_key="", model="claude-haiku")
    result = provider.generate(system_prompt="sys", user_prompt="test")
    assert result["model"] == "claude-haiku"


def test_mock_stream_uses_overridden_model(isolated_workspace_env):
    provider = AnthropicProvider(api_key="", model="claude-haiku")
    events = list(provider.generate_stream(system_prompt="sys", user_prompt="test"))
    completed = next(e for e in events if e["type"] == "response.completed")
    assert completed["response"]["model"] == "claude-haiku"
