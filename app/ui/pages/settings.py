# -*- coding: utf-8 -*-
"""设置页面：引擎状态、组件安装、默认参数、目录与关于。"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                               QWidget)

from ...core import asr
from ...core.config import CACHE_DIR, CONFIG, OUTPUT_DIR, ROOT
from ...core.engines.f5tts_engine import F5TTSEnvCheck
from ...core.engines.registry import all_engines
from .. import theme
from ..dialogs import InstallDialog
from ..widgets import Card, HLine, chip, muted, title

APP_VERSION = "1.0.0"


class SettingsPage(QWidget):
    statusMessage = Signal(str)
    enginesChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine_rows = {}
        self._build()

    def _build(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        host = QWidget()
        root = QVBoxLayout(host)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(title("设置"))
        head.addStretch(1)
        btn_recheck = QPushButton("重新检测")
        btn_recheck.setProperty("kind", "ghost")
        btn_recheck.clicked.connect(self.refresh)
        head.addWidget(btn_recheck)
        root.addLayout(head)

        # --- 引擎 ---
        c1 = Card()
        c1.body.addWidget(title("语音引擎", 2))
        c1.body.addWidget(muted(
            "「F5-TTS」用于音色克隆，需要下载模型（首次合成时自动下载）；"
            "「系统语音」无需模型，可立即跑通全流程。", tiny=True))
        c1.body.addWidget(HLine())
        for e in all_engines():
            row = QHBoxLayout()
            info = QVBoxLayout()
            info.setSpacing(2)
            lbl = QLabel(e.label)
            lbl.setStyleSheet("font-weight:600;")
            info.addWidget(lbl)
            desc = muted(e.description, tiny=True)
            desc.setWordWrap(True)
            info.addWidget(desc)
            if not e.packages:
                # 这类引擎（如 GPT-SoVITS）靠独立扩展包，pip 装不了：
                # 不给按钮，把获取方式写成一行提示，避免弹出空命令的安装窗。
                hint = muted(e.install_hint or "该引擎无需安装依赖。", tiny=True)
                hint.setWordWrap(True)
                info.addWidget(hint)
            row.addLayout(info, 1)

            status = chip("检测中…")
            row.addWidget(status, 0, Qt.AlignTop)
            btn = None
            if e.packages:
                btn = QPushButton("安装依赖")
                btn.setProperty("kind", "ghost")
                btn.clicked.connect(lambda _=False, eng=e: self._install(eng.packages,
                                                                         f"安装 {eng.label}"))
                row.addWidget(btn, 0, Qt.AlignTop)
            self._engine_rows[e.key] = (status, btn)
            c1.body.addLayout(row)
            c1.body.addWidget(HLine())
        root.addWidget(c1)

        # --- 可选组件 ---
        c2 = Card()
        c2.body.addWidget(title("可选组件", 2))
        row = QHBoxLayout()
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(QLabel("语音识别（faster-whisper）"))
        info.addWidget(muted("用于自动识别参考音频中的文字，省去手动输入。", tiny=True))
        row.addLayout(info, 1)
        self.chip_asr = chip("检测中…")
        row.addWidget(self.chip_asr, 0, Qt.AlignTop)
        btn_asr = QPushButton("安装")
        btn_asr.setProperty("kind", "ghost")
        btn_asr.clicked.connect(lambda: self._install(["faster-whisper"], "安装语音识别组件"))
        row.addWidget(btn_asr, 0, Qt.AlignTop)
        c2.body.addLayout(row)
        root.addWidget(c2)

        # --- 默认参数 ---
        c3 = Card()
        c3.body.addWidget(title("默认参数", 2))
        grid = QHBoxLayout()
        col1 = QVBoxLayout()
        col1.setSpacing(8)
        self.sp_chunk = self._spin_row(col1, "单段最大字符", int(CONFIG.get("max_chunk_chars") or 110), 30, 300)
        self.sp_gap = self._spin_row(col1, "段落间隔 (ms)", int(CONFIG.get("gap_ms") or 180), 0, 800, 20)
        col2 = QVBoxLayout()
        col2.setSpacing(8)
        self.dsp_rms = self._dspin_row(col2, "目标响度 RMS", float(CONFIG.get("target_rms") or 0.12), 0.03, 0.4)
        self.sp_nfe = self._spin_row(col2, "默认推理步数", int(CONFIG.get("nfe_step") or 24), 8, 64)
        grid.addLayout(col1, 1)
        grid.addLayout(col2, 1)
        c3.body.addLayout(grid)

        row = QHBoxLayout()
        self.cb_mp3 = QCheckBox("同时导出 MP3")
        self.cb_mp3.setChecked(bool(CONFIG.get("export_mp3")))
        self.cb_auto = QCheckBox("合成后自动播放")
        self.cb_auto.setChecked(bool(CONFIG.get("open_after_synth")))
        row.addWidget(self.cb_mp3)
        row.addWidget(self.cb_auto)
        row.addStretch(1)
        c3.body.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("模型下载镜像"))
        self.ed_mirror = QLineEdit(str(CONFIG.get("hf_endpoint") or "https://hf-mirror.com"))
        self.ed_mirror.setPlaceholderText("留空则直连 huggingface.co")
        row.addWidget(self.ed_mirror, 1)
        c3.body.addLayout(row)
        c3.body.addWidget(muted("国内网络建议保留默认镜像；修改后需重启软件生效。", tiny=True))

        btn_save = QPushButton("保存设置")
        btn_save.setProperty("kind", "primary")
        btn_save.clicked.connect(self._save)
        rowb = QHBoxLayout()
        rowb.addStretch(1)
        rowb.addWidget(btn_save)
        c3.body.addLayout(rowb)
        root.addWidget(c3)

        # --- 目录 ---
        c4 = Card()
        c4.body.addWidget(title("目录", 2))
        c4.body.addLayout(self._path_row("输出目录", str(CONFIG.output_dir()), "output"))
        c4.body.addLayout(self._path_row("模型缓存", str(CACHE_DIR / "hf"), "cache"))
        c4.body.addWidget(muted(f"程序目录：{ROOT}", tiny=True))
        root.addWidget(c4)

        # --- 关于 ---
        c5 = Card()
        c5.body.addWidget(title("关于", 2))
        c5.body.addWidget(muted(
            f"声纹工坊 VoiceClone Studio v{APP_VERSION}　·　"
            "本地离线运行的音色克隆工作台，支持中英文与 Unicode 混排文本。", tiny=True))
        c5.body.addWidget(muted(
            "由 B 站 @我是学编程的周二 开发　·　代码以 MIT 许可开源", tiny=True))
        self.lb_env = QPlainTextEdit()
        self.lb_env.setReadOnly(True)
        self.lb_env.setMaximumHeight(96)
        self.lb_env.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        c5.body.addWidget(self.lb_env)
        c5.body.addWidget(muted(
            "仅供个人学习与合法用途使用：请确保你拥有所使用音频的授权，"
            "不得用于伪造他人身份、诈骗或侵权。", tiny=True))
        root.addWidget(c5)
        root.addStretch(1)

        scroll.setWidget(host)
        self.refresh()

    # ------------------------------------------------------------------ #
    def _spin_row(self, layout, label: str, value: int, lo: int, hi: int,
                  step: int = 1) -> QSpinBox:
        row = QHBoxLayout()
        lb = QLabel(label)
        lb.setFixedWidth(120)
        row.addWidget(lb)
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setValue(value)
        row.addWidget(sp, 1)
        layout.addLayout(row)
        return sp

    def _dspin_row(self, layout, label: str, value: float, lo: float,
                   hi: float) -> QDoubleSpinBox:
        row = QHBoxLayout()
        lb = QLabel(label)
        lb.setFixedWidth(120)
        row.addWidget(lb)
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(0.01)
        sp.setDecimals(2)
        sp.setValue(value)
        row.addWidget(sp, 1)
        layout.addLayout(row)
        return sp

    def _path_row(self, label: str, path: str, kind: str) -> QHBoxLayout:
        row = QHBoxLayout()
        lb = QLabel(label)
        lb.setFixedWidth(120)
        row.addWidget(lb)
        ed = QLineEdit(path)
        ed.setReadOnly(True)
        row.addWidget(ed, 1)
        btn = QPushButton("打开")
        btn.setProperty("kind", "ghost")

        def _open():
            p = Path(ed.text())
            p.mkdir(parents=True, exist_ok=True)
            try:
                os.startfile(str(p))  # type: ignore[attr-defined]
            except Exception:
                pass

        btn.clicked.connect(_open)
        row.addWidget(btn)
        return row

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        for e in all_engines():
            ok, msg = e.available()
            status, btn = self._engine_rows[e.key]
            status.setText("已就绪" if ok else "未安装")
            status.setProperty("role", "chipOk" if ok else "chipWarn")
            status.style().unpolish(status)
            status.style().polish(status)
            status.setToolTip(msg)
            if btn is not None:
                btn.setVisible(not ok)
        ok, msg = asr.available()
        self.chip_asr.setText("已安装" if ok else "未安装")
        self.chip_asr.setProperty("role", "chipOk" if ok else "chipWarn")
        self.chip_asr.style().unpolish(self.chip_asr)
        self.chip_asr.style().polish(self.chip_asr)
        self.chip_asr.setToolTip(msg)
        self.lb_env.setPlainText(F5TTSEnvCheck.report())

    def _install(self, packages, title_text: str) -> None:
        if not packages:
            # 兜底：包名列表为空时 pip 会报 "You must give at least one requirement"，
            # 直接拦下来，别让用户看一条注定失败的日志。
            QMessageBox.information(
                self, "无需安装",
                "该引擎不通过 pip 安装，请按设置页上的说明获取对应扩展包。")
            return
        dlg = InstallDialog(list(packages), title_text, self)
        dlg.exec()
        self.refresh()
        if dlg.success:
            self.enginesChanged.emit()

    def _save(self) -> None:
        CONFIG.update(
            max_chunk_chars=self.sp_chunk.value(),
            gap_ms=self.sp_gap.value(),
            target_rms=round(float(self.dsp_rms.value()), 3),
            nfe_step=self.sp_nfe.value(),
            export_mp3=self.cb_mp3.isChecked(),
            open_after_synth=self.cb_auto.isChecked(),
            hf_endpoint=self.ed_mirror.text().strip(),
        )
        self.statusMessage.emit("设置已保存")
        QMessageBox.information(self, "已保存", "设置已保存。镜像等部分选项需重启软件后生效。")
