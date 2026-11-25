"""兼容 astrbot.api.event：事件对象、消息链与 filter 装饰器。

独立运行时这些钩子不会被 AstrBot 调用，装饰器只负责让类定义能正常执行。
"""
from __future__ import annotations

from typing import Any, Callable

HOOKS: dict[str, list[Callable]] = {}


def _register(kind: str):
    def decorator(func: Callable) -> Callable:
        HOOKS.setdefault(kind, []).append(func)
        return func

    return decorator


class _Filter:
    def on_llm_response(self):
        return _register("llm_response")

    def on_llm_request(self):
        return _register("llm_request")

    def on_decorating_result(self):
        return _register("decorating_result")

    def after_message_sent(self):
        return _register("after_message_sent")

    def llm_tool(self, name: str | None = None):
        return _register("tool")

    def command(self, name: str, alias: set[str] | None = None):
        return _register("command")


filter = _Filter()


class MessageChain:
    def __init__(self) -> None:
        self._text = ""

    def message(self, text: str) -> "MessageChain":
        self._text = str(text)
        return self

    def __str__(self) -> str:
        return self._text


class AstrMessageEvent:
    """独立运行时由 hook 桥构造的轻量事件。"""

    def __init__(self, text: str = "", umo: str = "local", private: bool = True, admin: bool = True) -> None:
        self.message_str = text
        self.unified_msg_origin = umo
        self._private = private
        self._admin = admin
        self._extra: dict[str, Any] = {}
        self._result: Any = None
        self._stopped = False

    def is_private_chat(self) -> bool:
        return self._private

    def is_admin(self) -> bool:
        return self._admin

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self._extra.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extra[key] = value

    def get_result(self) -> Any:
        return self._result

    def stop_event(self) -> None:
        self._stopped = True

    def plain_result(self, text: str) -> MessageChain:
        return MessageChain().message(text)
