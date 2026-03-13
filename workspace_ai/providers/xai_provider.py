from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List
from urllib.request import Request, urlopen

from workspace_ai.app.settings import get_settings
from workspace_ai.providers.base import LLMProvider


class XAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.xai_api_key
        self.default_model = model if model is not None else settings.default_model
        self.base_url = "https://api.x.ai/v1"

    def capabilities(self) -> Dict[str, Any]:
        return {
            "provider": "xai",
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
                "content": f"[mock:xai] {user_prompt[:400]}",
                "provider": "xai",
                "model": model or self.default_model,
                "mode": "mock",
                "usage": {},
            }
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in conversation or []:
            content = str(item.get("content") or "").strip()
            if content:
                messages.append({"role": str(item.get("role") or "user"), "content": content})
        messages.append({"role": "user", "content": user_prompt})
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps({"model": model or self.default_model, "messages": messages}).encode("utf-8"),
            headers={"Authorization": f"Bearer {active_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choice = payload.get("choices", [{}])[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        return {
            "content": str(message.get("content") or "").strip(),
            "provider": "xai",
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
            text = f"[mock:xai] {user_prompt[:400]}"
            for token in text.split():
                yield {"type": "response.output_text.delta", "delta": f"{token} "}
            yield {
                "type": "response.completed",
                "response": {"output_text": text, "provider": "xai", "model": model or self.default_model, "mode": "mock", "usage": {}},
            }
            return
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in conversation or []:
            content = str(item.get("content") or "").strip()
            if content:
                messages.append({"role": str(item.get("role") or "user"), "content": content})
        messages.append({"role": "user", "content": user_prompt})
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps({"model": model or self.default_model, "messages": messages, "stream": True}).encode("utf-8"),
            headers={"Authorization": f"Bearer {active_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    payload = json.loads(data)
                    choices = payload.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {}) if isinstance(choices[0], dict) else {}
                        text = str(delta.get("content") or "")
                        if text:
                            yield {"type": "response.output_text.delta", "delta": text}
                    finish_choices = payload.get("choices", [])
                    if finish_choices and finish_choices[0].get("finish_reason"):
                        yield {
                            "type": "response.completed",
                            "response": {
                                "output_text": "",
                                "provider": "xai",
                                "model": payload.get("model", model or self.default_model),
                                "mode": "live",
                                "usage": payload.get("usage", {}),
                            },
                        }
