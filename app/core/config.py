# -*- coding: utf-8 -*-
"""全局配置与路径管理。

两种运行形态：
1. 源码直接运行：代码目录即数据目录（voices/ output/ cache/ 与 main.py 同级）
2. 发行版运行：启动器传入 VCS_HOME / VCS_MODELS 环境变量，
   代码在 resources/app，数据在 resources/data，模型在 resources/models。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

# 代码根目录（源码模式 = 项目根；发行版 = resources/app）
CODE_ROOT = Path(__file__).resolve().parents[2]

# 数据根目录
_HOME = os.environ.get("VCS_HOME", "").strip()
DATA_ROOT = Path(_HOME) if _HOME else CODE_ROOT

ROOT = DATA_ROOT                      # 历史兼容
VOICES_DIR = DATA_ROOT / "voices"
OUTPUT_DIR = DATA_ROOT / "output"
CACHE_DIR = DATA_ROOT / "cache"
LOGS_DIR = DATA_ROOT / "logs"
ASSETS_DIR = CODE_ROOT / "assets"
CONFIG_FILE = DATA_ROOT / "config.json"

for _d in (VOICES_DIR, OUTPUT_DIR, CACHE_DIR, LOGS_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def models_dir() -> Path:
    """模型缓存目录：发行版指向 resources/models，源码模式用 cache/hf。"""
    env = os.environ.get("VCS_MODELS", "").strip()
    return Path(env) if env else (CACHE_DIR / "hf")


DEFAULTS: Dict[str, Any] = {
    "output_dir": str(OUTPUT_DIR),
    "engine": "f5tts",
    "device": "cpu",
    "nfe_step": 10,
    "cfg_strength": 2.0,
    "speed": 1.0,
    "gap_ms": 180,
    "max_chunk_chars": 110,
    "target_rms": 0.12,
    "asr_model": "base",
    "cpu_threads": 0,
    "export_mp3": False,
    "open_after_synth": True,
    "last_voice": "",
    "hf_endpoint": "https://hf-mirror.com",
}


class Config:
    """轻量 JSON 配置对象，读写即时落盘。"""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if k in DEFAULTS:
                            self._data[k] = v
                # 发行包被整体移动到别的盘时，输出目录要跟着数据根走
                out = str(self._data.get("output_dir") or "")
                if not out or not Path(out).parent.exists():
                    self._data["output_dir"] = str(OUTPUT_DIR)
            except Exception:
                pass

    def save(self) -> None:
        try:
            CONFIG_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def update(self, **kwargs: Any) -> None:
        self._data.update(kwargs)
        self.save()

    def output_dir(self) -> Path:
        p = Path(self.get("output_dir") or OUTPUT_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p


CONFIG = Config()
