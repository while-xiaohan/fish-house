"""兼容 astrbot.api.star：Star / Context。"""
from __future__ import annotations

from typing import Any, Callable

from . import logger


class Star:
    def __init__(self, context: Context, config: Any = None) -> None:
        self.context = context
        self.config = config


class Context:
    def __init__(self) -> None:
        self.web_apis: list[tuple[str, Callable, list[str], str]] = []
        self.sent_messages: list[tuple[str, Any]] = []

    def register_web_api(self, path: str, handler: Callable, methods: list[str], desc: str = "") -> None:
        self.web_apis.append((path, handler, list(methods), desc))

    async def send_message(self, umo: str, chain: Any) -> None:
        # 独立运行时没有 IM 侧；到达提示只记日志，方便排查时序。
        text = getattr(chain, "_text", "")
        self.sent_messages.append((umo, text))
        logger.info(f"[send] {umo}: {text}")
