# -*- coding: utf-8 -*-
"""引擎注册表。"""
from __future__ import annotations

from typing import List, Optional

from ..config import CONFIG
from .base import Engine, SynthRequest
from .f5tts_engine import F5TTSEngine
from .gptsovits_engine import GPTSoVITSEngine
from .system_engine import SystemEngine

# GPT-SoVITS 排在最前：多语言、模型小，在本机 CPU 上明显更快
_INSTANCES: List[Engine] = [GPTSoVITSEngine(), F5TTSEngine(), SystemEngine()]


def all_engines() -> List[Engine]:
    return list(_INSTANCES)


def get_engine(key: str) -> Optional[Engine]:
    for e in _INSTANCES:
        if e.key == key:
            return e
    return None


def default_engine() -> Engine:
    e = get_engine(str(CONFIG.get("engine")))
    if e is not None:
        return e
    for cand in _INSTANCES:
        if cand.available()[0]:
            return cand
    return _INSTANCES[0]
