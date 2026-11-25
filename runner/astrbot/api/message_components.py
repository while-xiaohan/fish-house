"""兼容 astrbot.api.message_components：只补 Comp.Plain。"""
from __future__ import annotations


class Plain:
    def __init__(self, text: str = "") -> None:
        self.text = text


class Comp:
    Plain = Plain
