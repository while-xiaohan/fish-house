#!/usr/bin/env python3
"""用 MediaKit 标准版 + AIGC 场景 + 1080p 重跑两套主题视频。

之前专业版不支持 scene，等于通用增强；这批是 AI 生成的动漫画面，
改用 standard / scene=aigc，才对这类低分辨率 AIGC 视频做超分和细节重绘。
"""
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


def json_from(text: str) -> dict:
    text = text.strip()
    start = text.find("{")
    if start < 0:
        raise ValueError(f"没有 JSON：{text[:200]}")
    return json.loads(text[start:])


def run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def submit(src: Path) -> str:
    cmd = [
        CLI, "video", "enhance-video",
        "--video-url", str(src),
        "--resolution", "1080p",
        "--tool-version", "standard",
        "--scene", "aigc",
        "--enhance-style", "hd",
        "--bitrate-level", "high",
        "--client-token", uuid.uuid4().hex,
    ]
    for attempt in range(3):
        try:
            p = run(cmd, timeout=120)
            data = json_from(p.stdout)
            tid = data.get("task_id")
            if tid:
                return tid
            raise RuntimeError(f"提交失败：{data}")
        except Exception as exc:
            if attempt == 2:
                raise
            print(f"提交重试 {src.name}: {exc}", flush=True)
            time.sleep(2)
    raise RuntimeError("unreachable")


def poll(task_id: str) -> str:
    last = ""
    consecutive_empty = 0
    for _ in range(160):
        try:
            p = run([CLI, "shared", "query-task", "--task-id", task_id], timeout=30)
            data = json_from(p.stdout)
            status = data.get("status")
            if status == "completed" and data.get("video_url"):
                return str(data["video_url"])
            if status in {"failed", "error", "cancelled"}:
                raise RuntimeError(f"任务失败 {task_id}: {data}")
            if not data.get("task_id") or str(data.get("task_id")) == "<nil>":
                consecutive_empty += 1
                if consecutive_empty > 20:
                    raise RuntimeError(f"查询持续返回空 {task_id}")
            else:
                consecutive_empty = 0
            last = json.dumps(data, ensure_ascii=False)
        except RuntimeError:
            raise
        except Exception as exc:
            last = str(exc)
        time.sleep(3)
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


def one(item: tuple[str, Path]) -> dict:
    tid, src = item
    out = THEMES / tid / "videos" / f"{src.stem}{SUFFIX}.mp4"
    if out.is_file() and out.stat().st_size > 10000:
        if not (DIST / out.name).is_file():
            shutil.copy2(out, DIST / out.name)
        print(f"[{tid}] 已存在 {out.name}，跳过", flush=True)
        return {"tid": tid, "src": src.name, "out": out.name, "elapsed": 0}
    started = time.time()
    task_id = submit(src)
    print(f"[{tid}] 提交 {src.name} -> {task_id}", flush=True)
    url = poll(task_id)
    raw = TMP / f"_aigc_{tid}_{src.stem}.mp4"
    download(url, raw)
    theme_vdir = THEMES / tid / "videos"
    theme_vdir.mkdir(parents=True, exist_ok=True)
    postprocess(raw, out)
    raw.unlink(missing_ok=True)
    shutil.copy2(out, DIST / out.name)
    elapsed = round(time.time() - started, 1)
    print(f"[{tid}] 完成 {out.name} {elapsed}s", flush=True)
    return {"tid": tid, "src": src.name, "out": out.name, "elapsed": elapsed}


def main() -> int:
    if not FFMPEG.is_file():
        print("ffmpeg 不存在", file=sys.stderr)
        return 2
    items: list[tuple[str, Path]] = []
    for theme_dir in sorted(p for p in THEMES.iterdir() if p.is_dir()):
        vdir = BACKUP / theme_dir.name
        if not vdir.is_dir():
            continue
        for src in sorted(vdir.glob("*.mp4")):
            if src.stem.endswith(("-hd", "-ai", SUFFIX)):
                continue
            items.append((theme_dir.name, src))
    print(f"待 AIGC 1080p 增强 {len(items)} 个视频", flush=True)

    results = []
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
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
            stem = Path(r["src"]).stem
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
    for r in results:
        print(f"{r['tid']} | {r['src']} -> {r['out']} | {r['elapsed']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
