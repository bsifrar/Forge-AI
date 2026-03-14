from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List
from urllib.request import Request, urlopen

from workspace_ai.app.settings import get_settings
from workspace_ai.providers.base import LLMProvider

_MAX_TOKENS = 4096


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key
        self.default_model = model if model is not None else settings.anthropic_default_model
        self.base_url = "https://api.anthropic.com/v1"

    def capabilities(self) -> Dict[str, Any]:
        return {
            "provider": "anthropic",
            "streaming": True,
            "responses_api": False,
            "files": False,
            "tools": [],
        }

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation: List[Dict[str, str]] | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> Dict[str, Any]:
        active_key = api_key or self.api_key
        if not active_key:
            return {
                "content": f"[mock:anthropic] {user_prompt[:400]}",
                "provider": "anthropic",
                "model": model or self.default_model,
                "mode": "mock",
                "usage": {},
            }
        messages: List[Dict[str, str]] = []
        for item in conversation or []:
            content = str(item.get("content") or "").strip()
            if content:
                messages.append({"role": str(item.get("role") or "user"), "content": content})
        messages.append({"role": "user", "content": user_prompt})
        request = Request(
            f"{self.base_url}/messages",
            data=json.dumps({
                "model": model or self.default_model,
                "max_tokens": _MAX_TOKENS,
                "system": system_prompt,
                "messages": messages,
            }).encode("utf-8"),
            headers={
                "x-api-key": active_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content_blocks = payload.get("content") or []
        text = "".join(
            str(block.get("text") or "")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        return {
            "content": text,
            "provider": "anthropic",
            "model": payload.get("model", model or self.default_model),
            "mode": "live",
            "usage": payload.get("usage", {}),
            "response_id": payload.get("id", ""),
        }

    def generate_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation: List[Dict[str, str]] | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> Iterable[Dict[str, Any]]:
        active_key = api_key or self.api_key
        if not active_key:
            text = f"[mock:anthropic] {user_prompt[:400]}"
            for token in text.split():
                yield {"type": "response.output_text.delta", "delta": f"{token} "}
            yield {
                "type": "response.completed",
                "response": {"output_text": text, "provider": "anthropic", "model": model or self.default_model, "mode": "mock", "usage": {}},
            }
            return
        messages: List[Dict[str, str]] = []
        for item in conversation or []:
            content = str(item.get("content") or "").strip()
            if content:
                messages.append({"role": str(item.get("role") or "user"), "content": content})
        messages.append({"role": "user", "content": user_prompt})
        request = Request(
            f"{self.base_url}/messages",
            data=json.dumps({
                "model": model or self.default_model,
                "max_tokens": _MAX_TOKENS,
                "system": system_prompt,
                "messages": messages,
                "stream": True,
            }).encode("utf-8"),
            headers={
                "x-api-key": active_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                event = json.loads(data)
                event_type = event.get("type", "")
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = str(delta.get("text") or "")
                        if text:
                            yield {"type": "response.output_text.delta", "delta": text}
                elif event_type == "message_stop":
                    yield {
                        "type": "response.completed",
                        "response": {
                            "output_text": "",
                            "provider": "anthropic",
                            "model": model or self.default_model,
                            "mode": "live",
                            "usage": {},
                        },
                    }
