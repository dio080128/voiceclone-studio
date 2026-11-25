# -*- coding: utf-8 -*-
"""通用控件：波形视图、播放条、卡片、指标徽标等。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import theme

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    HAS_MULTIMEDIA = True
except Exception:  # pragma: no cover
    HAS_MULTIMEDIA = False


# --------------------------------------------------------------------------- #
# 基础容器
# --------------------------------------------------------------------------- #

class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, margins: int = 18,
                 spacing: int = 12) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(spacing)


class HLine(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {theme.BORDER};")


def chip(text: str, kind: str = "chip") -> QLabel:
    role = {"ok": "chipOk", "warn": "chipWarn", "bad": "chipBad"}.get(kind, "chip")
    lb = QLabel(text)
    lb.setProperty("role", role)
    lb.setAlignment(Qt.AlignCenter)
    return lb


def muted(text: str, tiny: bool = False) -> QLabel:
    lb = QLabel(text)
    lb.setProperty("role", "tiny" if tiny else "muted")
    lb.setWordWrap(True)
    return lb


def title(text: str, level: int = 1) -> QLabel:
    lb = QLabel(text)
    lb.setProperty("role", "h1" if level == 1 else "h2")
    return lb


class MetricBox(QFrame):
    """竖排指标：数值 + 说明。"""

    def __init__(self, label: str, value: str = "—",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardFlat")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(2)
        self.value_lb = QLabel(value)
        f = QFont(theme.FONT_FAMILY, 13)
        f.setBold(True)
        self.value_lb.setFont(f)
        self.name_lb = QLabel(label)
        self.name_lb.setProperty("role", "tiny")
        lay.addWidget(self.value_lb)
        lay.addWidget(self.name_lb)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, text: str, color: str | None = None) -> None:
        self.value_lb.setText(text)
        if color:
            self.value_lb.setStyleSheet(f"color: {color};")


# --------------------------------------------------------------------------- #
# 波形
# --------------------------------------------------------------------------- #

class WaveformView(QWidget):
    """轻量波形显示，支持点击定位播放位置。"""

    seeked = Signal(float)

    def __init__(self, parent: QWidget | None = None, height: int = 92) -> None:
        super().__init__(parent)
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._env: Optional[tuple[np.ndarray, np.ndarray]] = None
        self._duration = 0.0
        self._progress = 0.0
        self._placeholder = "暂无音频"
        self._interactive = True

    # -- 数据 ---------------------------------------------------------------
    def clear(self, placeholder: str = "暂无音频") -> None:
        self._env = None
        self._duration = 0.0
        self._progress = 0.0
        self._placeholder = placeholder
        self.update()

    def set_audio(self, y: np.ndarray, sr: int) -> None:
        if y is None or len(y) == 0:
            self.clear()
            return
        y = np.asarray(y, dtype=np.float32)
        buckets = 1400
        n = len(y)
        step = max(1, n // buckets)
        usable = (n // step) * step
        if usable < step * 2:
            self.clear("音频过短")
            return
        frames = y[:usable].reshape(-1, step)
        mins = frames.min(axis=1)
        maxs = frames.max(axis=1)
        self._env = (mins, maxs)
        self._duration = n / sr if sr else 0.0
        self._progress = 0.0
        self.update()

    def set_progress(self, ratio: float) -> None:
        self._progress = max(0.0, min(1.0, float(ratio)))
        self.update()

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    # -- 事件 ---------------------------------------------------------------
    def mousePressEvent(self, ev) -> None:
        if not self._interactive or self._env is None or self._duration <= 0:
            return
        w = max(1, self.width() - 2)
        ratio = max(0.0, min(1.0, (ev.position().x() - 1) / w))
        self._progress = ratio
        self.update()
        self.seeked.emit(ratio)

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#F7F9FD"))
        p.drawRoundedRect(rect, 10, 10)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 10, 10)

        if self._env is None:
            p.setPen(QColor("#9AA3B0"))
            f = QFont(theme.FONT_FAMILY, 9)
            p.setFont(f)
            p.drawText(rect, Qt.AlignCenter, self._placeholder)
            return

        mins, maxs = self._env
        w = int(rect.width()) - 12
        h = rect.height() - 12
        x0 = rect.left() + 6
        mid = rect.center().y()
        # 时间轴淡线
        p.setPen(QPen(QColor("#E8ECF3"), 1))
        p.drawLine(int(x0), int(mid), int(x0 + w), int(mid))

        nb = len(mins)
        base = QColor("#BFCEE8")
        accent = QColor(theme.ACCENT)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#5B8BF0"))
        grad.setColorAt(1.0, QColor("#2E6BE6"))

        p.setPen(Qt.NoPen)
        for i in range(w):
            a = int(i * nb / w)
            b = max(a + 1, int((i + 1) * nb / w))
            lo = float(mins[a:b].min())
            hi = float(maxs[a:b].max())
            y1 = mid - hi * h / 2
            y2 = mid - lo * h / 2
            if y2 - y1 < 1:
                y2 = y1 + 1
            color = accent if (i / max(1, w)) <= self._progress else base
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x0 + i, y1, 0.9, y2 - y1), 0.45, 0.45)

        if self._duration > 0:
            p.setPen(QColor("#8A94A3"))
            p.setFont(QFont(theme.FONT_FAMILY, 8))
            p.drawText(QRectF(rect.left() + 8, rect.bottom() - 16, 60, 14),
                       Qt.AlignLeft | Qt.AlignVCenter, "0:00")
            p.drawText(QRectF(rect.right() - 68, rect.bottom() - 16, 60, 14),
                       Qt.AlignRight | Qt.AlignVCenter, fmt_time(self._duration))


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m, s = divmod(int(round(seconds)), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# --------------------------------------------------------------------------- #
# 播放条
# --------------------------------------------------------------------------- #

class PlayerBar(QWidget):
    """波形 + 播放控制，封装 QMediaPlayer。"""

    def __init__(self, parent: QWidget | None = None, show_open: bool = True) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.wave = WaveformView(self)
        lay.addWidget(self.wave)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn = QPushButton("▶  播放")
        self.btn.setFixedWidth(88)
        self.btn.setEnabled(False)
        row.addWidget(self.btn)

        self.time_lb = QLabel("0:00 / 0:00")
        self.time_lb.setProperty("role", "muted")
        row.addWidget(self.time_lb)
        row.addStretch(1)

        self.hint = QLabel("")
        self.hint.setProperty("role", "tiny")
        row.addWidget(self.hint)

        self.btn_open = QPushButton("打开文件夹")
        self.btn_open.setProperty("kind", "ghost")
        self.btn_open.setVisible(show_open)
        row.addWidget(self.btn_open)
        lay.addLayout(row)

        self._path: Optional[Path] = None
        self._player = None
        self._audio_out = None
        self._playing = False

        if HAS_MULTIMEDIA:
            self._player = QMediaPlayer(self)
            self._audio_out = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_out)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.playbackStateChanged.connect(self._on_state)
        else:
            self.hint.setText("未启用内置播放器（点击播放将用系统播放器打开）")

        self.btn.clicked.connect(self.toggle)
        self.btn_open.clicked.connect(self._open_folder)
        self.wave.seeked.connect(self.seek)

    # -- 公共 ---------------------------------------------------------------
    def load(self, path: str | Path, autoplay: bool = False) -> None:
        path = Path(path)
        if not path.exists():
            return
        self._path = path
        self.btn.setEnabled(True)
        self.time_lb.setText(f"0:00 / {fmt_time(_wav_duration(path))}")
        try:
            from ..core.audio_proc import read_audio
            y, sr = read_audio(path)
            self.wave.set_audio(y, sr)
        except Exception:
            self.wave.clear("无法预览波形")

        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(str(path)))
            if autoplay:
                self._player.play()

    def seek(self, ratio: float) -> None:
        if self._player is None or self._path is None:
            return
        dur = self._player.duration()
        if dur <= 0:
            dur = int(_wav_duration(self._path) * 1000)
        if dur > 0:
            self._player.setPosition(int(dur * ratio))

    def toggle(self) -> None:
        if self._player is None:
            self._open_external()
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            if self._player.position() >= self._player.duration() > 0:
                self._player.setPosition(0)
            self._player.play()

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()

    # -- 内部 ---------------------------------------------------------------
    def _open_folder(self) -> None:
        if self._path is None:
            return
        folder = str(self._path.parent)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass

    def _open_external(self) -> None:
        if self._path is None:
            return
        try:
            os.startfile(str(self._path))  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_position(self, pos: int) -> None:
        dur = self._player.duration() if self._player else 0
        if dur > 0:
            self.wave.set_progress(pos / dur)
            self.time_lb.setText(f"{fmt_time(pos / 1000)} / {fmt_time(dur / 1000)}")

    def _on_duration(self, dur: int) -> None:
        if dur > 0:
            self.time_lb.setText(f"0:00 / {fmt_time(dur / 1000)}")

    def _on_state(self, state) -> None:
        if self._player is None:
            return
        if state == QMediaPlayer.PlayingState:
            self.btn.setText("⏸  暂停")
        else:
            self.btn.setText("▶  播放")
            if state == QMediaPlayer.StoppedState:
                self.wave.set_progress(0.0)


def _wav_duration(path: Path) -> float:
    try:
        import soundfile as sf
        info = sf.info(str(path))
        return float(info.frames) / float(info.samplerate or 1)
    except Exception:
        return 0.0
