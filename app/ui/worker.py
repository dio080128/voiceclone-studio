# -*- coding: utf-8 -*-
"""后台任务线程：所有耗时操作（分析、合成、识别）都走这里，避免界面卡死。"""
from __future__ import annotations

import threading
import traceback
from typing import Callable

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    """执行 fn(emit, is_cancelled) -> result。

    emit(percent:int, message:str) 会以信号形式回到主线程。
    """

    progressed = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn
        self._evt = threading.Event()

    def cancel(self) -> None:
        self._evt.set()

    def is_cancelled(self) -> bool:
        return self._evt.is_set()

    def _emit(self, percent: int, message: str) -> None:
        self.progressed.emit(int(percent), str(message))

    def run(self) -> None:  # noqa: D102
        try:
            result = self._fn(self._emit, self.is_cancelled)
        except InterruptedError:
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).strip() or exc.__class__.__name__
            if self.is_cancelled():
                self.cancelled.emit()
                return
            self.failed.emit(f"{msg}\n{traceback.format_exc(limit=2)}")
            return
        self.succeeded.emit(result)
