"""兼容 astrbot.core.utils.astrbot_path.get_astrbot_data_path。"""
from __future__ import annotations

import os
from pathlib import Path


def get_astrbot_data_path() -> str:
    env = os.environ.get("FISH_HOUSE_DATA")
    if env:
        path = Path(env)
    else:
        path = Path(__file__).resolve().parents[3] / "data"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
