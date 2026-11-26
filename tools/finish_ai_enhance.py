#!/usr/bin/env python3
"""补齐新主题 5 段 AI 增强结果，并把主题引用从 -hd 切到 -ai。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

FFMPEG = Path(r"E:\AI\whale-cover\tools\ffmpeg\ffmpeg.exe")
DATA = Path(r"E:\AI\dsh-fish-house\data")
THEMES = DATA / "plugin_data" / "astrbot_plugin_fish_house" / "themes"
DIST = DATA / "dist" / "fish_house" / "videos"
TMP = Path(r"E:\AI\dsh-fish-house\tools")

POST_FILTER = (
    "scale=1280:720:force_original_aspect_ratio=decrease:flags=lanczos,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
    "unsharp=5:5:0.45:3:3:0.2"
)

TASKS = [
    ("asset_1794316414-8b109c", "https://aka.doubaocdn.com/s/IfHDdEAaZV"),
    ("asset_1794316415-ced776", "https://aka.doubaocdn.com/s/Df2DSM3PfU"),
    ("asset_1794319687-49a211", "https://aka.doubaocdn.com/s/KP5ADGLD9m"),
    ("asset_1794320123-b0617a", "https://aka.doubaocdn.com/s/3g2TeioUHH"),
    ("asset_1794317636-273441", "https://aka.doubaocdn.com/s/0VM63n6uMz"),
]
TID = "50756926fc"


def download(url: str, dst: Path) -> None:
    import urllib.request
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(url, dst)
            if dst.is_file() and dst.stat().st_size > 10000:
                return
            raise RuntimeError("下载文件太小")
        except Exception:
            if attempt == 2:
                raise


def postprocess(src: Path, dst: Path) -> None:
    subprocess.run([
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", POST_FILTER,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-map_metadata", "0", "-map", "0:v:0", "-map", "0:a?",
        str(dst),
    ], check=True)


def main() -> int:
    vdir = THEMES / TID / "videos"
    vdir.mkdir(parents=True, exist_ok=True)
    for stem, url in TASKS:
        out = vdir / f"{stem}-ai.mp4"
        if out.is_file() and out.stat().st_size > 10000:
            print(f"已存在 {out.name}，跳过")
        else:
            raw = TMP / f"_ai_{TID}_{stem}.mp4"
            download(url, raw)
            postprocess(raw, out)
            raw.unlink(missing_ok=True)
            print(f"完成 {out.name}")
        shutil.copy2(out, DIST / out.name)

    # 所有已有 -ai 文件都替换对应原生名 / -hd 名引用
    for theme_dir in sorted(p for p in THEMES.iterdir() if p.is_dir()):
        tf = theme_dir / "theme.json"
        if not tf.is_file():
            continue
        theme = json.loads(tf.read_text(encoding="utf-8"))
        cfg = theme.setdefault("config", {})
        mapping = {}
        for ai in (theme_dir / "videos").glob("*-ai.mp4"):
            base = ai.name[: -len("-ai.mp4")]
            mapping[f"{base}.mp4"] = ai.name
            mapping[f"{base}-hd.mp4"] = ai.name
            mapping[ai.name] = ai.name

        def swap(value):
            if not isinstance(value, str):
                return value
            b = os.path.basename(value)
            if b in mapping:
                return value[: -len(b)] + mapping[b]
            return value

        for node in (cfg.get("flow") or {}).get("nodes") or []:
            node["video"] = swap(node.get("video"))
        for k, val in list((cfg.get("videos") or {}).items()):
            cfg["videos"][k] = swap(val)
        for item in cfg.get("library") or []:
            item["video"] = swap(item.get("video"))
        tf.write_text(json.dumps(theme, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"theme.json 已更新：{tf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
