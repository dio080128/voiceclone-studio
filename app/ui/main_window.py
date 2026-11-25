# -*- coding: utf-8 -*-
"""主窗口：左侧导航 + 内容区。"""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..core.config import CONFIG
from ..core.engines.registry import default_engine
from ..core.profiles import VoiceStore
from . import theme
from .pages.batch import BatchPage
from .pages.library import LibraryPage
from .pages.settings import APP_VERSION, SettingsPage
from .pages.synth import SynthPage

NAV_ITEMS = [("语音合成", "合成"), ("音色库", "音色"), ("批量合成", "批量"), ("设置", "设置")]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = VoiceStore()
        self.setWindowTitle("声纹工坊 · VoiceClone Studio")
        geo = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1300, max(1080, geo.width() - 80)),
                    min(880, max(660, geo.height() - 60)))
        self.setMinimumSize(min(1080, geo.width() - 40), min(660, geo.height() - 40))

        root = QWidget()
        root.setObjectName("Root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.synth_page = SynthPage(self.store)
        self.library_page = LibraryPage(self.store)
        self.batch_page = BatchPage(self.store)
        self.settings_page = SettingsPage()
        for p in (self.synth_page, self.library_page, self.batch_page, self.settings_page):
            self.stack.addWidget(p)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.statusBar().showMessage("就绪")
        self._wire()
        self._switch(0)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_ctrl_enter)

    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(216)
        v = QVBoxLayout(bar)
        v.setContentsMargins(14, 18, 14, 14)
        v.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(theme.make_app_icon(72).pixmap(QSize(36, 36)))
        icon.setFixedSize(36, 36)
        brand.addWidget(icon)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        name = QLabel("声纹工坊")
        name.setProperty("role", "brand")
        sub = QLabel("VoiceClone Studio")
        sub.setProperty("role", "tiny")
        tv.addWidget(name)
        tv.addWidget(sub)
        brand.addLayout(tv)
        brand.addStretch(1)
        v.addLayout(brand)
        v.addSpacing(18)

        self.nav_buttons: List[QPushButton] = []
        for i, (text, _) in enumerate(NAV_ITEMS):
            b = QPushButton(text)
            b.setProperty("kind", "nav")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(38)
            b.clicked.connect(lambda _=False, idx=i: self._switch(idx))
            v.addWidget(b)
            self.nav_buttons.append(b)

        v.addStretch(1)

        # 鸣谢入口：放在导航区下方，和功能页区分开
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {theme.BORDER};")
        v.addWidget(line)
        self.btn_sponsors = QPushButton("♥   鸣谢名单")
        self.btn_sponsors.setProperty("kind", "nav")
        self.btn_sponsors.setCursor(Qt.PointingHandCursor)
        self.btn_sponsors.setMinimumHeight(34)
        self.btn_sponsors.setToolTip("感谢在爱发电支持这个项目的朋友")
        self.btn_sponsors.clicked.connect(self._show_sponsors)
        v.addWidget(self.btn_sponsors)
        v.addSpacing(8)

        tip = QLabel("本地离线运行 · 数据不出本机")
        tip.setProperty("role", "tiny")
        tip.setWordWrap(True)
        v.addWidget(tip)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setProperty("role", "tiny")
        v.addWidget(ver)
        return bar

    # ------------------------------------------------------------------ #
    def _wire(self) -> None:
        self.library_page.goSynthesize.connect(self._use_voice)
        self.library_page.voiceChanged.connect(self._on_voice_changed)
        self.synth_page.statusMessage.connect(self._status)
        self.batch_page.statusMessage.connect(self._status)
        self.settings_page.statusMessage.connect(self._status)
        self.settings_page.enginesChanged.connect(self._on_engines_changed)
        self.stack.currentChanged.connect(self._on_page_changed)

    def _switch(self, index: int) -> None:
        if index == 1:
            self.library_page.refresh()
        elif index == 2:
            self.batch_page.refresh()
            self.synth_page.refresh_voices()
        elif index == 0:
            self.synth_page.refresh_voices()
        elif index == 3:
            self.settings_page.refresh()

        for i, b in enumerate(self.nav_buttons):
            b.setProperty("kind", "navActive" if i == index else "nav")
            b.style().unpolish(b)
            b.style().polish(b)
        self.stack.setCurrentIndex(index)
        CONFIG.set("last_page", index)

    def _on_page_changed(self, index: int) -> None:
        names = [n[0] for n in NAV_ITEMS]
        if 0 <= index < len(names):
            self.statusBar().showMessage(names[index])

    def _status(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 8000)

    def _use_voice(self, profile) -> None:
        self._switch(0)
        self.synth_page.select_voice(profile)

    def _on_voice_changed(self, profile) -> None:
        self.synth_page.refresh_voices()

    def _on_engines_changed(self) -> None:
        self.synth_page.refresh_engines()
        self.batch_page.refresh()

    def _show_sponsors(self) -> None:
        from .sponsor_dialog import SponsorDialog

        SponsorDialog(self).exec()

    def _on_ctrl_enter(self) -> None:
        if self.stack.currentIndex() == 0:
            self.synth_page._run()

    # ------------------------------------------------------------------ #
    def closeEvent(self, ev) -> None:
        try:
            if self.synth_page._worker is not None and self.synth_page._worker.isRunning():
                self.synth_page._worker.cancel()
        except Exception:
            pass
        super().closeEvent(ev)
