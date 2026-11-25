"""兼容 astrbot.core.config.astrbot_config.AstrBotConfig（就当成带默认值的字典）。"""
from __future__ import annotations

from typing import Any


class AstrBotConfig(dict):
    def __init__(self, data: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(data or {})
        self.update(kwargs)

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        value = super().get(key, default)
        return default if value is None else value
