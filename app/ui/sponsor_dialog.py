# -*- coding: utf-8 -*-
"""鸣谢名单对话框：展示爱发电支持者。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from ..core import sponsors as sponsor_store
from . import theme
from .widgets import HLine, muted, title

ROLE_HIGHLIGHT = "sponsorChip"


class SponsorDialog(QDialog):
    """只读展示，数据由后台每天更新。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("鸣谢名单")
        self.setModal(True)
        screen = self.screen().availableGeometry() if self.screen() else None
        h = min(560, (screen.height() - 120) if screen else 560)
        self.resize(720, h)
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QWidget()
        hv = QVBoxLayout(head)
        hv.setContentsMargins(24, 20, 24, 10)
        hv.setSpacing(4)
        hv.addWidget(title("鸣谢名单"))

        board = sponsor_store.load()
        if board.sponsors:
            cnt = board.total or len(board.sponsors)
            hv.addWidget(muted(f"感谢这 {cnt} 位朋友的支持，让这个项目能继续做下去。"))
        else:
            hv.addWidget(muted("感谢每一位支持过这个项目的朋友。"))
        outer.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        body = QVBoxLayout(inner)
        body.setContentsMargins(24, 6, 24, 14)
        body.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        if not board.sponsors:
            empty = QLabel("名单还在路上\n\n感谢每一位默默支持这个项目的朋友")
            empty.setProperty("role", "tiny")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(160)
            body.addWidget(empty)
        else:
            grid = QGridLayout()
            grid.setSpacing(8)
            cols = 4
            for i, sp in enumerate(board.sponsors):
                grid.addWidget(self._chip(sp), i // cols, i % cols)
            for c in range(cols):
                grid.setColumnStretch(c, 1)
            body.addLayout(grid)
            body.addStretch(1)

        footer = QWidget()
        fv = QHBoxLayout(footer)
        fv.setContentsMargins(24, 8, 24, 16)
        left = muted(
            f"数据更新于 {board.updated}" if board.updated else "数据尚未更新",
            tiny=True)
        fv.addWidget(left)
        fv.addStretch(1)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        fv.addWidget(self.btn_close)
        outer.addWidget(HLine())
        outer.addWidget(footer)

    def _chip(self, sp) -> QWidget:
        w = QFrame()
        w.setObjectName("SponsorChip")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)
        name = QLabel(sp.name)
        name.setStyleSheet(f"color: {theme.TEXT}; font-weight: 600;")
        lay.addWidget(name)
        lay.addStretch(1)
        if sp.months and sp.months > 1:
            tag = QLabel(f"{sp.months} 个月")
            tag.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
            lay.addWidget(tag)
        return w
