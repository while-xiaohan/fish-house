"""大肥鱼的小屋 —— 独立运行壳。

把 AstrBot 插件原版逻辑（main.py / theme_store.py 一行不改）跑在本地 HTTP 服务上：
  * /panel/            管理面板
  * /fish_house/       公共壁纸页（可放 OBS / 当桌面壁纸）
  * /astrbot_plugin_fish_house/*   原插件注册的 18 个接口
  * /api/v1/plugins/extensions/astrbot_plugin_fish_house/*  面板直接调用的同义路径
  * /hook               给 DSH / 鲸鲸 用的状态驱动口
"""
from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
SRC = Path(os.environ.get("FISH_HOUSE_SRC") or (PKG / "upstream-v2.0.1"))
DATA = Path(os.environ.get("FISH_HOUSE_DATA") or (PKG / "data"))
os.environ["FISH_HOUSE_DATA"] = str(DATA)
os.environ["FISH_HOUSE_SRC"] = str(SRC)

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SRC))

from astrbot.api import logger  # noqa: E402
from astrbot.api.star import Context  # noqa: E402
from astrbot.api.web import JSONResponse, reset_current, set_current  # noqa: E402

API_PREFIX = "/api/v1/plugins/extensions"
PLUGIN_BASE = "/astrbot_plugin_fish_house"


class RequestShim:
    """模拟 AstrBot 的 request 对象。"""

    def __init__(self, handler: BaseHTTPRequestHandler, scheme: str = "http") -> None:
        self._handler = handler
        self.headers = handler.headers
        self.scheme = scheme
        self._body = handler._fish_body  # type: ignore[attr-defined]

    async def json(self, default=None):
        try:
            if not self._body:
                return default if default is not None else {}
            return json.loads(self._body.decode("utf-8"))
        except Exception:
            return default if default is not None else {}

    async def form(self):
        return {}


class FishHouseServer:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.closed = False

    async def start(self) -> None:
        DATA.mkdir(parents=True, exist_ok=True)
        dist = DATA / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        if not (dist / "index.html").is_file():
            (dist / "index.html").write_text("<!doctype html><meta charset=utf-8><title>fish house</title>", encoding="utf-8")

        from main import FishHousePlugin  # noqa: E402  (原版插件)

        self.context = Context()
        self.plugin = FishHousePlugin(self.context, {})
        self.routes = {}
        for path, handler, methods, _desc in self.context.web_apis:
            self.routes[path] = (handler, set(methods))
        logger.info(f"小屋已注册 {len(self.routes)} 个接口")
        await self.plugin.initialize()
        self.public_dir = self.plugin.public_dir
        logger.info(f"公共页面目录：{self.public_dir}")

    # ---------------------------------------------------------------- 分发
    async def call_route(self, name: str, request: RequestShim):
        plain = name.lstrip("/")
        path = "/" + plain if plain.startswith(PLUGIN_BASE.lstrip("/") + "/") else f"{PLUGIN_BASE}/{plain}"
        entry = self.routes.get(path)
        if entry is None:
            return JSONResponse({"status": "error", "message": f"没有这个接口：{name}"}, 404)
        handler, _methods = entry
        token = set_current(request)
        try:
            return await handler()
        finally:
            reset_current(token)


def make_handler(server: FishHouseServer, loop: asyncio.AbstractEventLoop):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FishHouse/2.0.1"

        def log_message(self, fmt: str, *args) -> None:  # 安静点
            if os.environ.get("FISH_HOUSE_VERBOSE"):
                logger.info(fmt % args)

        # -------------------------------------------------------- 工具
        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def send_error_json(self, status: int, message: str) -> None:
            self._send(status, json.dumps({"status": "error", "message": message}).encode(), "application/json; charset=utf-8")

        def _static(self, root: Path, rel: str) -> None:
            if not root:
                self.send_error_json(404, "公共页面还没准备好")
                return
            target = (root / rel).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                self.send_error_json(403, "越界路径")
                return
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                self.send_error_json(404, f"文件不存在：{rel}")
                return
            size = target.stat().st_size
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix.lower() in {".mp4", ".webm", ".mov", ".m4v"}:
                ctype = f"video/{target.suffix.lower().lstrip('.')}"
            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                try:
                    start_s, _, end_s = range_header[6:].partition("-")
                    start = int(start_s or 0)
                    end = int(end_s) if end_s else size - 1
                    end = min(end, size - 1)
                    length = max(0, end - start + 1)
                    self.send_response(206)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(length))
                    self.end_headers()
                    with target.open("rb") as handle:
                        handle.seek(start)
                        remaining = length
                        while remaining > 0:
                            chunk = handle.read(min(262144, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    return
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with target.open("rb") as handle:
                while True:
                    chunk = handle.read(262144)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        # -------------------------------------------------------- 入口
        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.end_headers()

        def do_HEAD(self) -> None:  # noqa: N802
            self._dispatch()

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self._fish_body = self.rfile.read(length) if length else b""  # type: ignore[attr-defined]
            self._dispatch()

        def _dispatch(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if not hasattr(self, "_fish_body"):
                self._fish_body = b""  # type: ignore[attr-defined]

            try:
                if path == "/health":
                    data = {"status": "ok", "mode": server.plugin.state.get("mode"), "prefix": server.plugin._prefix(), "port": server.port}
                    self._send(200, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")
                    return

                if path == "/hook":
                    payload = json.loads(self._fish_body.decode("utf-8") or "{}")
                    payload.setdefault("action", "reply")
                    self._fish_body = json.dumps(payload).encode()  # type: ignore[attr-defined]
                    self._route("event")
                    return

                if path == "/api/plugin/page/bridge-sdk.js":
                    self._send(200, b"/* standalone: no bridge needed */", "application/javascript; charset=utf-8")
                    return

                if path.startswith(API_PREFIX + "/"):
                    name = path[len(API_PREFIX) + 1:]
                    self._route(name)
                    return

                if path.startswith("/panel"):
                    rel = path[len("/panel"):].lstrip("/") or "index.html"
                    self._static(SRC / "pages" / "panel", rel)
                    return

                if path in {"/", "/index.html"}:
                    self.send_response(302)
                    self.send_header("Location", "/panel/")
                    self.end_headers()
                    return

                if path.startswith("/fish_house"):
                    rel = path[len("/fish_house"):].lstrip("/") or "index.html"
                    self._static(server.public_dir, rel)
                    return

                self.send_error_json(404, f"未知路径：{path}")
            except Exception as exc:  # noqa: BLE001
                logger.error(f"处理 {path} 出错：{exc}")
                logger.error(traceback.format_exc())
                self.send_error_json(500, str(exc))

        def _route(self, name: str) -> None:
            request = RequestShim(self)
            coro = server.call_route(name, request)
            result = self._run(coro)
            self._reply(result)

        def _run(self, fn):
            if asyncio.iscoroutine(fn):
                coro = fn
            else:
                coro = fn()
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=600)

        def _reply(self, result) -> None:
            if isinstance(result, JSONResponse):
                body = json.dumps(result.payload, ensure_ascii=False).encode()
                self._send(result.status_code, body, "application/json; charset=utf-8")
            elif isinstance(result, (dict, list)):
                self._send(200, json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif isinstance(result, bytes):
                self._send(200, result, "application/octet-stream")
            elif result is None:
                self._send(200, b"", "text/plain; charset=utf-8")
            else:
                self._send(200, str(result).encode(), "text/plain; charset=utf-8")

    return Handler


# ---------------------------------------------------------------- 睡衣模式调度
# 不再写死某一个主题的节点 id：按当前主题画布里的「睡衣 / 休息」标签找节点。
# 新主题如果没有睡衣节点（比如「小肥鱼的零食」），调度自动跳过，不再每 20 秒失败。
PAJAMA_START_HOUR = 23          # 晚上 11 点自动换睡衣
PAJAMA_END_HOUR = 7             # 早上 7 点自动换回日常


def want_pajama(now=None) -> bool:
    """当前时刻是不是「睡觉的点儿」。"""
    now = now or time.localtime()
    hour = now.tm_hour
    return hour >= PAJAMA_START_HOUR or hour < PAJAMA_END_HOUR


def start_pajama_scheduler(server: "FishHouseServer", loop) -> threading.Thread:
    """到点切睡衣/切回日常；状态被保存项目等操作打回休息时，也会自动补切。"""
    state = {"pajama": None}

    def pajama_node() -> str:
        try:
            node = server.plugin.flow_pajama_node()
            return str((node or {}).get("id") or "")
        except Exception:  # noqa: BLE001
            return ""

    def day_node() -> str:
        try:
            node = server.plugin.flow_day_node()
            return str((node or {}).get("id") or "")
        except Exception:  # noqa: BLE001
            return ""

    def switching_state() -> tuple[bool, str, str]:
        plugin = server.plugin
        mode = str(plugin.state.get("mode") or "")
        node = str(plugin.state.get("node_id") or "")
        label = str(plugin.state.get("node_label") or "")
        is_pajama = mode == "flow" and (
            node == pajama_node() or "睡衣" in label
        )
        return is_pajama, mode, node

    def switch(node_id: str, reason: str) -> None:
        if not node_id:
            return

        async def go():
            try:
                await server.plugin.flow_goto(node_id)
                logger.info(f"睡衣调度：{reason} → 节点 {node_id}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"睡衣调度切换失败（{node_id}）：{exc}")

        asyncio.run_coroutine_threadsafe(go(), loop)

    def run() -> None:
        while True:
            try:
                sleep_node = pajama_node()
                day = day_node()
                if not sleep_node:
                    # 当前主题没有睡衣节点，直接跳过整套调度。
                    state["pajama"] = None
                    time.sleep(20)
                    continue
                want = want_pajama()
                first = state["pajama"] is None
                is_pajama, _mode, _node = switching_state()

                if want:
                    # 11 点后如果因为保存项目/应用主题被踢回日常休息，20 秒内补回睡衣。
                    state["pajama"] = True
                    if not is_pajama:
                        switch(
                            sleep_node,
                            "启动时按当前时间补一次"
                            if first
                            else f"{PAJAMA_START_HOUR} 点后检测到不在睡衣状态，补切",
                        )
                else:
                    state["pajama"] = False
                    if is_pajama and day:
                        switch(
                            day,
                            "启动时按当前时间补一次"
                            if first
                            else f"{PAJAMA_END_HOUR} 点后检测到还在睡衣状态，切回日常",
                        )
            except Exception:  # noqa: BLE001
                logger.warning("睡衣调度出错：%s", traceback.format_exc())
            time.sleep(20)

    thread = threading.Thread(target=run, name="fish-house-pajama", daemon=True)
    thread.start()
    return thread


async def main_async(host: str, port: int) -> None:
    server = FishHouseServer(host, port)
    await server.start()
    loop = asyncio.get_running_loop()
    httpd = ThreadingHTTPServer((host, port), make_handler(server, loop))
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, name="fish-house-http", daemon=True)
    thread.start()
    start_pajama_scheduler(server, loop)
    logger.info(f"小屋已启动：http://{host}:{port}/panel/    壁纸页：http://{host}:{port}/fish_house/index.html")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        httpd.shutdown()


def cli() -> None:
    parser = argparse.ArgumentParser(description="大肥鱼的小屋 · 独立运行")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8899)
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
