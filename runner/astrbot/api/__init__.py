"""astrbot.api 的兼容实现：只提供 fish_house 实际用到的部分。"""
from __future__ import annotations

import logging

logger = logging.getLogger("fish_house")

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
