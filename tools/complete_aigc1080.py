#!/usr/bin/env python3
"""补齐 AIGC 1080p 增强：已提交的任务直接取结果，剩余低并发提交，最后统一更新引用。"""
from __future__ import annotations

import concurrent.futures as cf
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

CLI = shutil.which("mediakit-cli") or "mediakit-cli"
FFMPEG = Path(r"E:\AI\whale-cover\tools\ffmpeg\ffmpeg.exe")
DATA = Path(r"E:\AI\dsh-fish-house\data")
THEMES = DATA / "plugin_data" / "astrbot_plugin_fish_house" / "themes"
DIST = DATA / "dist" / "fish_house" / "videos"
BACKUP = Path(r"E:\AI\dsh-fish-house\tools\video-backup-20261126")
TMP = Path(r"E:\AI\dsh-fish-house\tools")

POST_FILTER = (
    "scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
)
SUFFIX = "-aigc1080"

# 已经提交成功、但主脚本查询超时的任务；stem -> (task_id, video_url)
KNOWN = {
    "asset_aac45d74e33e41aa98055be3e6e6763a-508bf8": ("amk-tool-enhance-video-1934563438082", "https://aka.doubaocdn.com/s/daA8ph307k"),
    "asset_d69070fcb0f74bf2bf7ae70e43c067f8-2a5775": ("amk-tool-enhance-video-2350593267458", "https://aka.doubaocdn.com/s/5lV69nUeWS"),
    "theme_91dd19b1cd_computer_go-63a339-6381b2-c4dc57-12322b": ("amk-tool-enhance-video-1934398382594", "https://aka.doubaocdn.com/s/kDi6oTqRrL"),
    "theme_91dd19b1cd_computer_loop-c07166-70e55c-0cd346-9cf259": ("amk-tool-enhance-video-1880036327426", "https://aka.doubaocdn.com/s/7qMtN4p56y"),
    "theme_91dd19b1cd_computer_rest-08ff97-de9fad-77cfd0-fc30a9": ("amk-tool-enhance-video-2350697865474", "https://aka.doubaocdn.com/s/02kP48XOe4"),
}

_lock = None


def json_from(text: str) -> dict:
    text = text.strip()
    start = text.find("{")
    if start < 0:
        raise ValueError(f"没有 JSON：{text[:200]}")
    return json.loads(text[start:])


def run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def submit(src: Path, token: str) -> str:
    cmd = [
        CLI, "video", "enhance-video",
        "--video-url", str(src),
        "--resolution", "1080p",
        "--tool-version", "standard",
        "--scene", "aigc",
        "--enhance-style", "hd",
        "--bitrate-level", "high",
        "--client-token", token,
    ]
    for attempt in range(5):
        try:
            p = run(cmd, timeout=120)
            data = json_from(p.stdout)
            tid = data.get("task_id")
            if tid:
                return tid
            raise RuntimeError(f"提交失败：{data}")
        except Exception as exc:
            if attempt == 4:
                raise
            wait = 8 * (attempt + 1)
            print(f"提交重试 {src.name} ({wait}s): {exc}", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def poll(task_id: str) -> str:
    last = ""
    empty = 0
    for _ in range(200):
        try:
            p = run([CLI, "shared", "query-task", "--task-id", task_id], timeout=30)
            data = json_from(p.stdout)
            status = data.get("status")
            if status == "completed" and data.get("video_url"):
                return str(data["video_url"])
            if status in {"failed", "error", "cancelled"}:
                raise RuntimeError(f"任务失败 {task_id}: {data}")
            if not data.get("task_id") or str(data.get("task_id")) == "<nil>":
                empty += 1
            else:
                empty = 0
            last = json.dumps(data, ensure_ascii=False)
        except RuntimeError:
            raise
        except Exception as exc:
            last = str(exc)
        time.sleep(6)
    raise RuntimeError(f"查询超时 {task_id}: {last[:300]}")


def download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(url, dst)
            if dst.is_file() and dst.stat().st_size > 10000:
                return
            raise RuntimeError("下载文件太小")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def postprocess(src: Path, dst: Path) -> None:
    cmd = [
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", POST_FILTER,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-map_metadata", "0", "-map", "0:v:0", "-map", "0:a?",
        str(dst),
    ]
    subprocess.run(cmd, check=True)


def finish(tid: str, stem: str, url: str) -> dict:
    out = THEMES / tid / "videos" / f"{stem}{SUFFIX}.mp4"
    if out.is_file() and out.stat().st_size > 10000:
        if not (DIST / out.name).is_file():
            shutil.copy2(out, DIST / out.name)
        print(f"[{tid}] 已存在 {out.name}", flush=True)
        return {"tid": tid, "stem": stem, "out": out.name}
    raw = TMP / f"_aigc_{tid}_{stem}.mp4"
    download(url, raw)
    out.parent.mkdir(parents=True, exist_ok=True)
    postprocess(raw, out)
    raw.unlink(missing_ok=True)
    shutil.copy2(out, DIST / out.name)
    print(f"[{tid}] 完成 {out.name}", flush=True)
    return {"tid": tid, "stem": stem, "out": out.name}


def one(item: tuple[str, Path]) -> dict:
    tid, src = item
    stem = src.stem
    out = THEMES / tid / "videos" / f"{stem}{SUFFIX}.mp4"
    if out.is_file() and out.stat().st_size > 10000:
        return finish(tid, stem, "")
    if stem in KNOWN:
        task_id, url = KNOWN[stem]
        print(f"[{tid}] 取已有任务 {task_id}", flush=True)
        return finish(tid, stem, url)
    time.sleep(2)
    token = uuid.uuid4().hex
    task_id = submit(src, token)
    print(f"[{tid}] 提交 {src.name} -> {task_id}", flush=True)
    url = poll(task_id)
    return finish(tid, stem, url)


def main() -> int:
    items: list[tuple[str, Path]] = []
    for theme_dir in sorted(p for p in THEMES.iterdir() if p.is_dir()):
        vdir = BACKUP / theme_dir.name
        if not vdir.is_dir():
            continue
        for src in sorted(vdir.glob("*.mp4")):
            if src.stem.endswith(("-hd", "-ai", SUFFIX)):
                continue
            items.append((theme_dir.name, src))
    print(f"共 {len(items)} 个，补齐未完成项", flush=True)

    results = []
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(one, item) for item in items]
        for fut in cf.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:
                print(f"失败：{exc}", flush=True)

    if len(results) != len(items):
        print(f"只成功 {len(results)}/{len(items)}，不更新引用", file=sys.stderr)
        return 3

    for theme_dir in sorted(p for p in THEMES.iterdir() if p.is_dir()):
        tf = theme_dir / "theme.json"
        if not tf.is_file():
            continue
        theme = json.loads(tf.read_text(encoding="utf-8"))
        cfg = theme.setdefault("config", {})
        mapping = {}
        for r in results:
            if r["tid"] != theme_dir.name:
                continue
            stem = r["stem"]
            mapping[f"{stem}.mp4"] = r["out"]
            mapping[f"{stem}-hd.mp4"] = r["out"]
            mapping[f"{stem}-ai.mp4"] = r["out"]
            mapping[f"{stem}{SUFFIX}.mp4"] = r["out"]

        def swap(value):
            if not isinstance(value, str):
                return value
            base = value.replace("\\", "/").split("/")[-1]
            if base in mapping:
                return value[: -len(base)] + mapping[base]
            return value

        for node in (cfg.get("flow") or {}).get("nodes") or []:
            node["video"] = swap(node.get("video"))
        for key, value in list((cfg.get("videos") or {}).items()):
            cfg["videos"][key] = swap(value)
        for item in cfg.get("library") or []:
            item["video"] = swap(item.get("video"))
        tf.write_text(json.dumps(theme, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"theme.json 已更新：{tf}", flush=True)

    print("\n全部完成：")
    for r in sorted(results, key=lambda x: (x["tid"], x["stem"])):
        print(f"{r['tid']} | {r['stem']} -> {r['out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
