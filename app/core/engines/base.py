# -*- coding: utf-8 -*-
"""语音引擎抽象层。引擎以插件方式注册，界面只依赖统一接口。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple


@dataclass
class SynthRequest:
    """一次合成请求。"""
    text: str = ""
    out_path: Path = Path("out.wav")
    ref_wav: str = ""
    ref_text: str = ""
    language: str = "auto"
    speed: float = 1.0
    nfe: int = 24
    cfg: float = 2.0
    seed: int = -1
    target_rms: float = 0.12
    progress: Optional[Callable[[str], None]] = None
    should_cancel: Optional[Callable[[], bool]] = None

    def log(self, msg: str) -> None:
        if self.progress:
            self.progress(msg)

    def cancelled(self) -> bool:
        return bool(self.should_cancel and self.should_cancel())


class Engine:
    """所有引擎的基类。"""

    key: str = "base"
    label: str = "引擎"
    kind: str = "clone"          # clone = 音色克隆，system = 系统语音
    description: str = ""
    packages: List[str] = []      # pip 包名，用于一键安装；空 = 不能靠 pip 装
    # packages 为空时的说明：告诉用户该去哪儿拿（例如独立的扩展包），
    # 界面不会再给「安装依赖」按钮——否则会执行一条没有任何包名的 pip 命令。
    install_hint: str = ""
    needs_model: bool = False

    def __init__(self) -> None:
        self._ready = False

    # -- 状态 ---------------------------------------------------------------
    def available(self) -> Tuple[bool, str]:
        """返回 (是否可用, 说明)。子类实现。"""
        return False, "未实现"

    def load(self, progress: Optional[Callable[[str], None]] = None) -> None:
        """惰性加载模型。"""

    def unload(self) -> None:
        self._ready = False

    # -- 合成 ---------------------------------------------------------------
    def synth_chunk(self, text: str, req: SynthRequest, out_wav: Path) -> Path:
        raise NotImplementedError

    # -- 辅助 ---------------------------------------------------------------
    def supports_profile(self) -> bool:
        return self.kind == "clone"
