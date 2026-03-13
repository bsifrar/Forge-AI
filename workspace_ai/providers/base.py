from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, *, system_prompt: str, user_prompt: str, conversation: List[Dict[str, str]] | None = None, model: str | None = None, api_key: str | None = None) -> Dict[str, Any]:
        ...

    @abstractmethod
    def generate_stream(self, *, system_prompt: str, user_prompt: str, conversation: List[Dict[str, str]] | None = None, model: str | None = None, api_key: str | None = None) -> Iterable[Dict[str, Any]]:
        ...

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        ...
