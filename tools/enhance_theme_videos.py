#!/usr/bin/env python3
"""批量把鱼屋主题视频统一到 1280x720 / 高码率清晰版。

- 原文件不改名、不覆盖，生成 `<原名>-hd.mp4`
- 同步复制到公共页 videos 目录
- 更新两个主题的 theme.json 引用，保留原素材可回退
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

FFMPEG = Path(r"E:\AI\whale-cover\tools\ffmpeg\ffmpeg.exe")
FFPROBE = Path(r"E:\AI\whale-cover\tools\ffmpeg\ffprobe.exe")
DATA = Path(r"E:\AI\dsh-fish-house\data")
THEMES = DATA / "plugin_data" / "astrbot_plugin_fish_house" / "themes"
DIST = DATA / "dist" / "fish_house" / "videos"
BACKUP = Path(r"E:\AI\dsh-fish-house\tools\video-backup-20261126")
CONFIG = DATA / "plugin_data" / "astrbot_plugin_fish_house" / "config.json"
ACTIVE_ID = "50756926fc"

FILTER = (
    "scale=1280:720:force_original_aspect_ratio=decrease:flags=lanczos,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
    "unsharp=5:5:0.8:3:3:0.3"
)


def probe(path: Path) -> dict:
    out = subprocess.check_output(
        [
            str(FFPROBE), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate,duration",
            "-show_entries", "format=size,bit_rate",
            "-of", "json", str(path),
        ],
        text=True,
    )
    return json.loads(out)


def enhance(src: Path, dst: Path) -> dict:
    cmd = [
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", FILTER,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-map_metadata", "0", "-map", "0:v:0", "-map", "0:a?",
        str(dst),
    ]
    t0 = time.time()
    subprocess.run(cmd, check=True)
    info = probe(dst)
    info["elapsed"] = round(time.time() - t0, 1)
    return info


def swap_path(value, mapping: dict[str, str]):
    if not isinstance(value, str):
        return value
    base = os.path.basename(value)
    new_base = mapping.get(base)
    if not new_base:
        return value
    return value[: -len(base)] + new_base if base else value


def main() -> int:
    if not FFMPEG.is_file():
        print("ffmpeg 不存在", file=sys.stderr)
        return 2
    BACKUP.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    theme_dirs = sorted(p for p in THEMES.iterdir() if p.is_dir())
    results = []

    for theme_dir in theme_dirs:
        vdir = theme_dir / "videos"
        if not vdir.is_dir():
            continue
        for src in sorted(vdir.glob("*.mp4")):
            if src.stem.endswith("-hd"):
                continue
            out = vdir / f"{src.stem}-hd.mp4"
            bak = BACKUP / theme_dir.name / src.name
            bak.parent.mkdir(parents=True, exist_ok=True)
            if not bak.exists():
                shutil.copy2(src, bak)

            before = probe(src)
            if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
                info = enhance(src, out)
            else:
                info = probe(out)
            mapping[src.name] = out.name

            w = info["streams"][0]["width"]
            h = info["streams"][0]["height"]
            bitrate = round(int(info["format"].get("bit_rate") or 0) / 1000)
            size_mb = round(int(info["format"].get("size") or 0) / 1024 / 1024, 2)
            results.append((theme_dir.name, src.name, out.name, w, h, bitrate, size_mb))
            print(
                f"[{theme_dir.name}] {src.name} -> {out.name} "
                f"{w}x{h} {bitrate}kbps {size_mb}MB {info.get('elapsed', '?')}s",
                flush=True,
            )

    # 复制到公共页目录（如果同一文件名已存在旧副本，保留旧文件，新增 hd 不需要覆盖）
    DIST.mkdir(parents=True, exist_ok=True)
    for theme_dir in theme_dirs:
        for src in sorted((theme_dir / "videos").glob("*-hd.mp4")):
            target = DIST / src.name
            shutil.copy2(src, target)

    # 更新主题 JSON 里的引用
    for theme_dir in theme_dirs:
        tf = theme_dir / "theme.json"
        if not tf.is_file():
            continue
        theme = json.loads(tf.read_text(encoding="utf-8"))
        cfg = theme.setdefault("config", {})
        for node in (cfg.get("flow") or {}).get("nodes") or []:
            node["video"] = swap_path(node.get("video"), mapping)
        for key, value in list((cfg.get("videos") or {}).items()):
            cfg["videos"][key] = swap_path(value, mapping)
        for item in cfg.get("library") or []:
            item["video"] = swap_path(item.get("video"), mapping)
        tf.write_text(json.dumps(theme, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"theme.json 已更新：{tf}", flush=True)

    # 更新当前运行配置里的槽位引用（画布节点走 theme.json，槽位走 config.json）
    if CONFIG.is_file():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        for key, value in list((cfg.get("videos") or {}).items()):
            cfg["videos"][key] = swap_path(value, mapping)
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"config.json 槽位已更新：{CONFIG}", flush=True)

    print("\n完成：")
    for row in results:
        print(" | ".join(str(x) for x in row))
    print(f"\nactive_theme={ACTIVE_ID}；备份目录={BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
