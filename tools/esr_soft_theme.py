#!/usr/bin/env python3
"""用 Real-ESRGAN（anime video 模型）把主题里的 1080p 视频再做一次
2x 细节重建，然后降采样回 1080p，并与原 1080p 以 80:20 混合。

目标不是重新生成，而是在现有 AI 自然版上补回更细的线稿和发丝，
同时用混合保留原本柔和的观感，避免锐化成硬边。
输出 <原名去掉 -natural1080>-soft1080.mp4。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FFMPEG = Path(r"E:\AI\whale-cover\tools\ffmpeg\ffmpeg.exe")
FFPROBE = Path(r"E:\AI\whale-cover\tools\ffmpeg\ffprobe.exe")
ESR = Path(r"E:\AI\dsh-fish-house\tools\realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe")
ESR_MODELS = Path(r"E:\AI\dsh-fish-house\tools\realesrgan-ncnn-vulkan\models")
DATA = Path(r"E:\AI\dsh-fish-house\data")
THEMES = DATA / "plugin_data" / "astrbot_plugin_fish_house" / "themes"
DIST = DATA / "dist" / "fish_house" / "videos"

FILTER = (
    "[0:v]scale=1920:1080:flags=lanczos[up];"
    "[1:v]scale=1920:1080:flags=lanczos[base];"
    "[up][base]blend=all_expr='A*0.80+B*0.20'[v]"
)


def run(cmd: list[str], timeout: int = 1200) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(
            f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr[-3000:]}"
        )


def probe(path: Path) -> tuple[float, int, int]:
    p = subprocess.run(
        [
            str(FFPROBE), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration",
            "-show_entries", "format=duration", "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(p.stdout)
    stream = data["streams"][0]
    rate = stream.get("r_frame_rate") or "24/1"
    num, den = rate.split("/")
    fps = float(num) / float(den or 1)
    duration = float(stream.get("duration") or data.get("format", {}).get("duration") or 0)
    return fps, int(stream["width"]), int(stream["height"])


def process(src: Path, dst: Path) -> None:
    fps, w, h = probe(src)
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="fish-esr-", dir=r"E:\AI\dsh-fish-house\tools") as tmp:
        t = Path(tmp)
        frames_in = t / "in"
        frames_out = t / "out"
        frames_in.mkdir()
        frames_out.mkdir()
        print(f"  extract {src.name} {w}x{h} {fps:.3f}fps", flush=True)
        run([
            str(FFMPEG), "-hide_banner", "-y", "-i", str(src),
            "-fps_mode", "passthrough", "-start_number", "1",
            str(frames_in / "%06d.png"),
        ])
        count = len(list(frames_in.glob("*.png")))
        print(f"  esr {count} frames", flush=True)
        run([
            str(ESR), "-i", str(frames_in), "-o", str(frames_out),
            "-n", "realesr-animevideov3", "-s", "2", "-m", str(ESR_MODELS),
            "-f", "png", "-j", "2:4:4",
        ])
        print(f"  encode", flush=True)
        run([
            str(FFMPEG), "-hide_banner", "-y",
            "-framerate", f"{fps:.6f}", "-start_number", "1",
            "-i", str(frames_out / "%06d.png"),
            "-i", str(src),
            "-filter_complex", FILTER,
            "-map", "[v]", "-map", "1:a?",
            "-c:v", "libx264", "-crf", "17", "-preset", "medium",
            "-tune", "animation", "-profile:v", "high", "-level", "4.1",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest",
            str(dst),
        ])
    print(f"  done {dst.name} in {time.time()-started:.0f}s", flush=True)


def update_theme(theme_id: str) -> None:
    tf = THEMES / theme_id / "theme.json"
    theme = json.loads(tf.read_text(encoding="utf-8"))
    cfg = theme.setdefault("config", {})

    def swap(value):
        if not isinstance(value, str):
            return value
        base = value.replace("\\", "/").split("/")[-1]
        if base.endswith("-natural1080.mp4"):
            return value[: -len(base)] + base.replace("-natural1080.mp4", "-soft1080.mp4")
        return value

    for node in (cfg.get("flow") or {}).get("nodes") or []:
        node["video"] = swap(node.get("video"))
    for item in cfg.get("library") or []:
        item["video"] = swap(item.get("video"))
    for key, value in list((cfg.get("videos") or {}).items()):
        cfg["videos"][key] = swap(value)
    tf.write_text(json.dumps(theme, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"theme.json updated: {tf}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", required=True)
    args = ap.parse_args()
    theme_id = args.theme
    vdir = THEMES / theme_id / "videos"
    sources = sorted(vdir.glob("*natural1080.mp4"))
    if not sources:
        print("no natural1080 inputs", file=sys.stderr)
        return 2
    print(f"theme {theme_id}: {len(sources)} clips", flush=True)
    for src in sources:
        dst = vdir / (src.name[: -len("-natural1080.mp4")] + "-soft1080.mp4")
        if dst.is_file() and dst.stat().st_size > 10000:
            print(f"skip existing {dst.name}", flush=True)
            continue
        process(src, dst)
        shutil.copy2(dst, DIST / dst.name)
    update_theme(theme_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
