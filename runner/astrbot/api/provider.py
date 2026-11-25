"""兼容 astrbot.api.provider：LLMResponse / ProviderRequest。"""
from __future__ import annotations

from typing import Any


class LLMResponse:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def __str__(self) -> str:
        return self.text


class ProviderRequest:
    def __init__(self, prompt: str = "") -> None:
        self.prompt = prompt
        self.system_prompt = ""
        self.extra: dict[str, Any] = {}
