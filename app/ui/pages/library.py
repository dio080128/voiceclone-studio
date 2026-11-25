# -*- coding: utf-8 -*-
"""音色库页面：导入素材、管理音色、编辑参考文本。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from ...core import asr
from ...core.profiles import VoiceProfile, VoiceStore
from .. import theme
from ..dialogs import NewVoiceDialog
from ..widgets import Card, HLine, MetricBox, PlayerBar, chip, muted, title
from ..worker import Worker


class _VoiceRow(QWidget):
    def __init__(self, p: VoiceProfile) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(2)
        f = QFont(theme.FONT_FAMILY, 10)
        f.setBold(True)
        name = QLabel(p.name)
        name.setFont(f)
        sub = QLabel(f"{p.duration:.1f}s · 质量 {p.quality} · "
                     f"{'有参考文本' if p.ref_text.strip() else '缺少参考文本'}")
        sub.setProperty("role", "tiny")
        lay.addWidget(name)
        lay.addWidget(sub)


class LibraryPage(QWidget):
    voiceChanged = Signal(object)
    goSynthesize = Signal(object)

    def __init__(self, store: VoiceStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._current: Optional[VoiceProfile] = None
        self._worker: Optional[Worker] = None
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # ---------------- 左侧列表 ----------------
        left = Card(margins=14, spacing=10)
        left.setFixedWidth(320)
        head = QHBoxLayout()
        head.addWidget(title("音色库"))
        self.count_chip = chip("0 个")
        head.addStretch(1)
        head.addWidget(self.count_chip)
        left.body.addLayout(head)
        left.body.addWidget(muted("每个音色 = 一段参考音频 + 对应文字", tiny=True))

        self.list = QListWidget()
        self.list.setSpacing(0)
        self.list.currentItemChanged.connect(self._on_select)
        left.body.addWidget(self.list, 1)

        self.btn_new = QPushButton("＋  新建音色（导入素材）")
        self.btn_new.setProperty("kind", "primary")
        self.btn_new.clicked.connect(self.create_voice)
        left.body.addWidget(self.btn_new)

        row = QHBoxLayout()
        self.btn_del = QPushButton("删除音色")
        self.btn_del.setProperty("kind", "danger")
        self.btn_del.setEnabled(False)
        self.btn_del.clicked.connect(self._delete)
        row.addWidget(self.btn_del)
        left.body.addLayout(row)
        root.addWidget(left)

        # ---------------- 右侧详情 ----------------
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_placeholder())
        self.stack.addWidget(self._build_detail())
        root.addWidget(self.stack, 1)

    def _build_placeholder(self) -> QWidget:
        w = Card()
        lay = QVBoxLayout()
        lay.setSpacing(8)
        lay.addStretch(1)
        lb = QLabel("还没有选中音色")
        lb.setAlignment(Qt.AlignCenter)
        lb.setProperty("role", "h2")
        lay.addWidget(lb)
        tip = muted("点击左侧「新建音色」导入 5~15 秒的清晰人声素材，\n"
                    "软件会自动清洗并建立可复用的音色档案。")
        tip.setAlignment(Qt.AlignCenter)
        lay.addWidget(tip)
        lay.addStretch(1)
        w.body.addLayout(lay)
        return w

    def _build_detail(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = Card()
        head = QHBoxLayout()
        self.ed_name = QLineEdit()
        f = QFont(theme.FONT_FAMILY, 13)
        f.setBold(True)
        self.ed_name.setFont(f)
        self.ed_name.setFrame(False)
        self.ed_name.setStyleSheet(
            "QLineEdit{background:transparent; border:none; padding:2px;}"
            f"QLineEdit:focus{{border-bottom:1px solid {theme.ACCENT};}}")
        head.addWidget(self.ed_name, 1)
        self.chip_q = chip("质量 —")
        self.chip_dur = chip("— s")
        self.chip_lang = chip("—")
        head.addWidget(self.chip_q)
        head.addWidget(self.chip_dur)
        head.addWidget(self.chip_lang)
        card.body.addLayout(head)
        card.body.addWidget(HLine())
        card.body.addWidget(QLabel("音色试听（参考音频）"))
        self.player = PlayerBar(show_open=True)
        card.body.addWidget(self.player)
        outer.addWidget(card)

        card2 = Card()
        row = QHBoxLayout()
        row.addWidget(title("参考文本", 2))
        row.addStretch(1)
        self.btn_asr = QPushButton("自动识别")
        self.btn_asr.setProperty("kind", "ghost")
        self.btn_asr.clicked.connect(self._auto_asr)
        row.addWidget(self.btn_asr)
        card2.body.addLayout(row)
        card2.body.addWidget(muted(
            "这里必须填写参考音频中「实际说出的内容」，逐字对应。"
            "文本不对齐会明显影响克隆相似度。", tiny=True))
        self.txt_ref = QPlainTextEdit()
        self.txt_ref.setPlaceholderText("例：今天天气不错，我们来聊聊语音合成的原理。")
        card2.body.addWidget(self.txt_ref, 1)
        outer.addWidget(card2, 1)

        bar = QHBoxLayout()
        self.btn_save = QPushButton("保存修改")
        self.btn_save.clicked.connect(self._save)
        self.btn_synth = QPushButton("用这个音色合成 →")
        self.btn_synth.setProperty("kind", "primary")
        self.btn_synth.clicked.connect(self._use)
        bar.addWidget(self.btn_save)
        bar.addStretch(1)
        bar.addWidget(self.btn_synth)
        outer.addLayout(bar)
        return page

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        keep = self._current.id if self._current else None
        voices = self.store.list()
        self.list.blockSignals(True)
        self.list.clear()
        target_row = -1
        for i, p in enumerate(voices):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 54))
            item.setData(Qt.UserRole, p.id)
            self.list.addItem(item)
            self.list.setItemWidget(item, _VoiceRow(p))
            if keep and p.id == keep:
                target_row = i
        self.list.blockSignals(False)
        self.count_chip.setText(f"{len(voices)} 个")

        if not voices:
            self._current = None
            self.stack.setCurrentIndex(0)
            self.btn_del.setEnabled(False)
            self.voiceChanged.emit(None)
            return

        if target_row < 0:
            target_row = 0
        self.list.setCurrentRow(target_row)
        self._on_select(self.list.currentItem(), None)

    def _on_select(self, cur: Optional[QListWidgetItem], _prev) -> None:
        if cur is None:
            return
        vid = cur.data(Qt.UserRole)
        profile = self.store.get(vid)
        if profile is None:
            return
        self._current = profile
        self.stack.setCurrentIndex(1)
        self.btn_del.setEnabled(True)

        self.ed_name.setText(profile.name)
        self.txt_ref.setPlainText(profile.ref_text)
        self.chip_q.setText(f"质量 {profile.quality}")
        self.chip_q.setProperty("role", "chipOk" if profile.quality >= 80 else "chip")
        self.chip_q.style().unpolish(self.chip_q)
        self.chip_q.style().polish(self.chip_q)
        self.chip_dur.setText(f"{profile.duration:.1f} 秒")
        self.chip_lang.setText({"zh": "中文", "en": "英文", "mix": "中英混合"}.get(profile.lang, "—"))
        self.player.load(profile.wav_path)
        self.btn_asr.setEnabled(asr.available()[0])
        self.btn_asr.setToolTip("" if asr.available()[0] else asr.available()[1])
        self.voiceChanged.emit(profile)

    # ------------------------------------------------------------------ #
    def create_voice(self) -> None:
        dlg = NewVoiceDialog(self.store, self)
        if dlg.exec() and dlg.created is not None:
            self._current = dlg.created
            self.refresh()

    def _save(self) -> None:
        if self._current is None:
            return
        name = self.ed_name.text().strip() or self._current.name
        self._current.name = name
        self._current.ref_text = self.txt_ref.toPlainText().strip()
        self.store.save(self._current)
        self.refresh()
        self.voiceChanged.emit(self._current)

    def _delete(self) -> None:
        if self._current is None:
            return
        ret = QMessageBox.question(
            self, "删除音色",
            f"确定删除「{self._current.name}」吗？参考音频文件会一起移除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.store.delete(self._current.id)
        self._current = None
        self.refresh()

    def _use(self) -> None:
        if self._current is None:
            return
        if not self._current.ref_text.strip():
            QMessageBox.information(self, "提示", "请先填写参考文本并保存。")
            return
        self.goSynthesize.emit(self._current)

    def _auto_asr(self) -> None:
        if self._current is None:
            return
        ok, msg = asr.available()
        if not ok:
            QMessageBox.warning(self, "需要安装组件",
                                "自动识别需要 faster-whisper，请在「设置 → 组件安装」中安装。")
            return
        wav = self._current.wav_path
        self.btn_asr.setEnabled(False)

        def job(emit, is_cancelled):
            return asr.transcribe(wav, progress=lambda m: emit(50, m))

        w = Worker(job, self)
        self._worker = w

        def done(text: str) -> None:
            self.btn_asr.setEnabled(True)
            if self._current:
                self.txt_ref.setPlainText(text)
                QMessageBox.information(self, "识别完成",
                                        "已填入参考文本，请核对无误后点击「保存修改」。")

        def fail(m: str) -> None:
            self.btn_asr.setEnabled(True)
            QMessageBox.warning(self, "识别失败", m.split("\n")[0])

        w.succeeded.connect(done)
        w.failed.connect(fail)
        w.finished.connect(w.deleteLater)
        w.start()

    def current_profile(self) -> Optional[VoiceProfile]:
        return self._current
