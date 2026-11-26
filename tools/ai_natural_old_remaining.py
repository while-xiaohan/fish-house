#!/usr/bin/env python3
"""补齐旧主题剩余的自然版 1080p，并更新旧主题引用。"""
from __future__ import annotations

import concurrent.futures as cf
import json
import shutil
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

CLI = shutil.which("mediakit-cli") or "mediakit-cli"
FFMPEG = Path(r"E:\AI\whale-cover\tools\ffmpeg\ffmpeg.exe")
THEMES = Path(r"E:\AI\dsh-fish-house\data\plugin_data\astrbot_plugin_fish_house\themes")
DIST = Path(r"E:\AI\dsh-fish-house\data\dist\fish_house\videos")
BACKUP = Path(r"E:\AI\dsh-fish-house\tools\video-backup-20261126")
TMP = Path(r"E:\AI\dsh-fish-house\tools")
TID = "47b36706"
SUFFIX = "-natural1080"


def run(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def json_from(text):
    s = text.strip(); i = s.find("{")
    if i < 0: raise ValueError(text[:200])
    return json.loads(s[i:])


def submit(src):
    for attempt in range(5):
        try:
            p = run([CLI, "video", "enhance-video", "--video-url", str(src),
                     "--resolution", "1080p", "--tool-version", "professional",
                     "--enhance-style", "natural", "--bitrate-level", "high",
                     "--client-token", uuid.uuid4().hex], 120)
            d = json_from(p.stdout)
            if d.get("task_id"): return d["task_id"]
            raise RuntimeError(d)
        except Exception as e:
            if attempt == 4: raise
            time.sleep(10 * (attempt + 1))
            print(f"提交重试 {src.name}: {e}", flush=True)


def poll(tid):
    for _ in range(160):
        try:
            p = run([CLI, "shared", "query-task", "--task-id", tid], 30)
            d = json_from(p.stdout)
            if d.get("status") == "completed" and d.get("video_url"): return d["video_url"]
            if d.get("status") in {"failed", "error", "cancelled"}: raise RuntimeError(d)
        except Exception as e:
            print(f"查询重试 {tid}: {str(e)[:120]}", flush=True)
        time.sleep(8)
    raise RuntimeError(f"超时 {tid}")


def post(src, dst):
    subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(src), "-vf",
                    "scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1",
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-tune", "animation", "-profile:v", "high", "-level", "4.1",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", "-map_metadata", "0",
                    "-map", "0:v:0", "-map", "0:a?", str(dst)], check=True)


def one(src):
    stem = src.stem
    out = THEMES / TID / "videos" / f"{stem}{SUFFIX}.mp4"
    if out.is_file() and out.stat().st_size > 10000:
        print(f"已存在 {out.name}", flush=True)
    else:
        task = submit(src)
        print(f"提交 {src.name} -> {task}", flush=True)
        url = poll(task)
        raw = TMP / f"_oldnat_{stem}.mp4"
        urllib.request.urlretrieve(url, raw)
        post(raw, out)
        raw.unlink(missing_ok=True)
        shutil.copy2(out, DIST / out.name)
        print(f"完成 {out.name}", flush=True)
    if not (DIST / out.name).is_file():
        shutil.copy2(out, DIST / out.name)
    return stem, out.name


def main():
    vdir = BACKUP / TID
    items = [p for p in sorted(vdir.glob("*.mp4")) if not p.stem.endswith(("-hd", "-ai", "-aigc1080", SUFFIX))]
    print(f"旧主题待补 {len(items)} 个", flush=True)
    results = []
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        for fut in cf.as_completed([pool.submit(one, s) for s in items]):
            try: results.append(fut.result())
            except Exception as e: print(f"失败：{e}", flush=True)
    if len(results) != len(items):
        print(f"只成功 {len(results)}/{len(items)}", flush=True)
        return 3
    tf = THEMES / TID / "theme.json"
    t = json.loads(tf.read_text(encoding="utf-8")); cfg = t.setdefault("config", {})
    mapping = {}
    for stem, name in results:
        for s in (".mp4", "-hd.mp4", "-ai.mp4", "-aigc1080.mp4", SUFFIX + ".mp4"):
            mapping[f"{stem}{s}"] = name
    # 已存在但不在本轮结果里的 natural 文件也要映射
    for f in (THEMES / TID / "videos").glob(f"*{SUFFIX}.mp4"):
        stem = f.name[: -len(f"{SUFFIX}.mp4")]
        for s in (".mp4", "-hd.mp4", "-ai.mp4", "-aigc1080.mp4", SUFFIX + ".mp4"):
            mapping[f"{stem}{s}"] = f.name

    import os
    def swap(v):
        if not isinstance(v, str): return v
        b = os.path.basename(v.replace("\\", "/"))
        return v[: -len(b)] + mapping[b] if b in mapping else v
    for n in (cfg.get("flow") or {}).get("nodes") or []: n["video"] = swap(n.get("video"))
    for k, v in list((cfg.get("videos") or {}).items()): cfg["videos"][k] = swap(v)
    for i in cfg.get("library") or []: i["video"] = swap(i.get("video"))
    tf.write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
    print("旧主题 theme.json 已更新", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
