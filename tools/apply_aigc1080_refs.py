#!/usr/bin/env python3
"""把旧主题已有 -aigc1080 文件应用到 theme.json 引用。"""
import json
import os
from pathlib import Path

THEMES = Path(r"E:\AI\dsh-fish-house\data\plugin_data\astrbot_plugin_fish_house\themes")


def apply_theme(theme_dir: Path) -> int:
    tf = theme_dir / "theme.json"
    theme = json.loads(tf.read_text(encoding="utf-8"))
    cfg = theme.setdefault("config", {})
    mapping = {}
    for ai in (theme_dir / "videos").glob("*-aigc1080.mp4"):
        stem = ai.name[: -len("-aigc1080.mp4")]
        mapping[f"{stem}.mp4"] = ai.name
        mapping[f"{stem}-hd.mp4"] = ai.name
        mapping[f"{stem}-ai.mp4"] = ai.name
        mapping[ai.name] = ai.name

    def swap(value):
        if not isinstance(value, str):
            return value
        base = os.path.basename(value.replace("\\", "/"))
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
    print(f"{theme_dir.name}: {len(list((theme_dir / 'videos').glob('*-aigc1080.mp4')))} 个 1080p 文件")
    print(f"  nodes: {[n.get('video') for n in (cfg.get('flow') or {}).get('nodes') or []]}")
    print(f"  videos: {list((cfg.get('videos') or {}).values())}")
    return 0


for d in sorted(p for p in THEMES.iterdir() if p.is_dir()):
    apply_theme(d)
