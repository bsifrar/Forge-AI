from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List
from urllib.request import Request, urlopen

from workspace_ai.app.settings import get_settings
from workspace_ai.providers.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.default_model = model if model is not None else settings.default_model
        self.base_url = "https://api.openai.com/v1"

    def capabilities(self) -> Dict[str, Any]:
        return {
            "provider": "openai",
            "streaming": True,
            "responses_api": True,
            "files": False,
            "tools": [],
        }

    def _extract_output_text(self, payload: Dict[str, Any]) -> str:
        text = payload.get("output_text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return ""

    def generate(self, *, system_prompt: str, user_prompt: str, conversation: List[Dict[str, str]] | None = None, model: str | None = None, api_key: str | None = None) -> Dict[str, Any]:
        active_key = api_key or self.api_key
        if not active_key:
            return {
                "content": f"[mock] {user_prompt[:400]}",
                "provider": "openai",
                "model": model or self.default_model,
                "mode": "mock",
                "usage": {},
            }
        input_items: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in conversation or []:
            content = str(item.get("content") or "").strip()
            if content:
                input_items.append({"role": str(item.get("role") or "user"), "content": content})
        input_items.append({"role": "user", "content": user_prompt})
        request = Request(
            f"{self.base_url}/responses",
            data=json.dumps({"model": model or self.default_model, "input": input_items}).encode("utf-8"),
            headers={"Authorization": f"Bearer {active_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "content": self._extract_output_text(payload),
            "provider": "openai",
            "model": payload.get("model", model or self.default_model),
            "mode": "live",
            "usage": payload.get("usage", {}),
            "response_id": payload.get("id", ""),
        }

    def generate_stream(self, *, system_prompt: str, user_prompt: str, conversation: List[Dict[str, str]] | None = None, model: str | None = None, api_key: str | None = None) -> Iterable[Dict[str, Any]]:
        active_key = api_key or self.api_key
        if not active_key:
            text = f"[mock] {user_prompt[:400]}"
            for token in text.split():
                yield {"type": "response.output_text.delta", "delta": f"{token} "}
            yield {"type": "response.completed", "response": {"output_text": text, "provider": "openai", "model": model or self.default_model, "mode": "mock", "usage": {}}}
            return
        input_items: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in conversation or []:
            content = str(item.get("content") or "").strip()
            if content:
                input_items.append({"role": str(item.get("role") or "user"), "content": content})
        input_items.append({"role": "user", "content": user_prompt})
        request = Request(
            f"{self.base_url}/responses",
            data=json.dumps({"model": model or self.default_model, "input": input_items, "stream": True}).encode("utf-8"),
            headers={"Authorization": f"Bearer {active_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data and data != "[DONE]":
                        yield json.loads(data)
