"""兼容 astrbot.api.web：json_response / error_response / 当前请求代理。"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any


class JSONResponse:
    """真实 AstrBot 返回的是 FastAPI Response；这里换成可序列化的壳。"""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def __repr__(self) -> str:  # pragma: no cover - 仅调试
        return f"JSONResponse({self.status_code}, {self.payload!r})"


class _RequestProxy:
    def __getattr__(self, name: str) -> Any:
        req = _CURRENT.get()
        if req is None:
            raise RuntimeError("当前没有活跃的 HTTP 请求")
        return getattr(req, name)


_CURRENT: ContextVar[Any] = ContextVar("fish_house_request", default=None)

request = _RequestProxy()


def set_current(req: Any):
    return _CURRENT.set(req)


def reset_current(token) -> None:
    _CURRENT.reset(token)


def json_response(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code)


def error_response(message: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"status": "error", "message": str(message)}, status_code)
