# -*- coding: utf-8 -*-
"""语音合成页面。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSizePolicy, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from ...core.config import CONFIG
from ...core.engines.base import Engine
from ...core.engines.registry import all_engines, default_engine, get_engine
from ...core.profiles import VoiceProfile, VoiceStore
from ...core.synth import SynthResult, synthesize, text_report
from .. import theme
from ..dialogs import TextCheckDialog
from ..widgets import Card, MetricBox, PlayerBar, chip, muted, title
from ..worker import Worker

SAMPLE_TEXT = (
    "你好，我是你的专属配音员。这是第 2 次测试：2026 年 11 月 9 日，气温 18℃，湿度 45%。"
    "Success rate 达到 99.7%，欢迎收听《声纹工坊》FM 3.5 频道。"
)


class SynthPage(QWidget):
    statusMessage = Signal(str)

    def __init__(self, store: VoiceStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._worker: Optional[Worker] = None
        self._last: Optional[SynthResult] = None
        self._t0 = 0.0
        self._last_msg = ""
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._build()
        self.refresh_voices()
        self.refresh_engines()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # ---------------- 左：音色与参数 ----------------
        left = QWidget()
        left.setFixedWidth(330)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(12)

        c1 = Card(margins=16, spacing=10)
        c1.body.addWidget(title("音色", 2))
        self.cmb_voice = QComboBox()
        self.cmb_voice.currentIndexChanged.connect(self._on_voice)
        c1.body.addWidget(self.cmb_voice)
        self.lb_voice = muted("")
        c1.body.addWidget(self.lb_voice)
        lv.addWidget(c1)

        c2 = Card(margins=16, spacing=12)
        c2.body.addWidget(title("引擎与参数", 2))
        self.cmb_engine = QComboBox()
        self.cmb_engine.currentIndexChanged.connect(self._on_engine)
        c2.body.addWidget(self.cmb_engine)
        self.lb_desc = muted("")
        c2.body.addWidget(self.lb_desc)
        self.lb_engine = muted("")
        c2.body.addWidget(self.lb_engine)

        self.sl_speed, self.lb_speed = self._slider_row(
            c2.body, "语速", 50, 180, 100, "×", scale=100)
        self.sl_cfg, self.lb_cfg = self._slider_row(
            c2.body, "相似度 CFG", 100, 400, 200, "", scale=100)
        self.sl_nfe, self.lb_nfe = self._slider_row(
            c2.body, "推理步数", 4, 64, int(CONFIG.get("nfe_step") or 10))

        row = QHBoxLayout()
        row.addWidget(QLabel("段落间隔"))
        self.sp_gap = QSpinBox()
        self.sp_gap.setRange(0, 800)
        self.sp_gap.setSingleStep(20)
        self.sp_gap.setValue(int(CONFIG.get("gap_ms") or 180))
        self.sp_gap.setSuffix(" ms")
        row.addWidget(self.sp_gap, 1)
        c2.body.addLayout(row)
        c2.body.addWidget(muted("步数越高越稳、越慢，纯 CPU 建议 8~12；CFG 越像参考音色，过高会失真。", tiny=True))
        lv.addWidget(c2)

        self.btn_reset = QPushButton("恢复默认参数")
        self.btn_reset.setProperty("kind", "ghost")
        self.btn_reset.clicked.connect(self._reset_params)
        lv.addWidget(self.btn_reset)

        tips = Card(margins=16, spacing=6)
        tips.body.addWidget(title("小贴士", 2))
        for t in ("参考音频 5~15 秒、环境安静、语气平稳，克隆最像",
                  "参考文本必须与音频逐字一致，否则相似度会明显下降",
                  "首次使用 F5-TTS 会自动下载约 1.4GB 模型",
                  "Ctrl + Enter 可直接开始合成"):
            tips.body.addWidget(muted("· " + t, tiny=True))
        lv.addWidget(tips)
        lv.addStretch(1)
        root.addWidget(left)

        # ---------------- 右：文本与结果 ----------------
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(12)

        c3 = Card(margins=16, spacing=10)
        head = QHBoxLayout()
        head.addWidget(title("朗读文本", 2))
        head.addStretch(1)
        self.lb_chars = muted("0 字")
        head.addWidget(self.lb_chars)
        c3.body.addLayout(head)

        self.txt = QPlainTextEdit()
        self.txt.setPlaceholderText("在这里输入要合成的文字，支持中文、英文、数字、标点混排…\n"
                                    "长文本会自动按句子切分后逐段合成。")
        self.txt.setMinimumHeight(120)
        self.txt.textChanged.connect(self._on_text)
        c3.body.addWidget(self.txt, 1)

        tools = QHBoxLayout()
        self.btn_check = QPushButton("检查文本 / 切句预览")
        self.btn_check.setProperty("kind", "ghost")
        self.btn_check.clicked.connect(self._check_text)
        self.btn_sample = QPushButton("填入示例")
        self.btn_sample.setProperty("kind", "ghost")
        self.btn_sample.clicked.connect(lambda: self.txt.setPlainText(SAMPLE_TEXT))
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setProperty("kind", "ghost")
        self.btn_clear.clicked.connect(self.txt.clear)
        tools.addWidget(self.btn_check)
        tools.addWidget(self.btn_sample)
        tools.addWidget(self.btn_clear)
        tools.addStretch(1)
        self.lb_len = muted("")
        tools.addWidget(self.lb_len)
        c3.body.addLayout(tools)
        rv.addWidget(c3, 1)

        c4 = Card(margins=16, spacing=12)
        row = QHBoxLayout()
        self.btn_run = QPushButton("开始合成")
        self.btn_run.setProperty("kind", "primary")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setMinimumWidth(150)
        self.btn_run.clicked.connect(self._run)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setMinimumHeight(40)
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_stop)
        row.addSpacing(8)
        self.lb_state = muted("准备就绪")
        row.addWidget(self.lb_state, 1)
        c4.body.addLayout(row)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        c4.body.addWidget(self.bar)

        self.player = PlayerBar()
        self.player.setVisible(False)
        c4.body.addWidget(self.player)

        mrow = QHBoxLayout()
        self.m_dur = MetricBox("音频时长", "—")
        self.m_cost = MetricBox("合成耗时", "—")
        self.m_chunks = MetricBox("切分段数", "—")
        self.m_engine = MetricBox("使用引擎", "—")
        for w in (self.m_dur, self.m_cost, self.m_chunks, self.m_engine):
            mrow.addWidget(w)
        c4.body.addLayout(mrow)
        self._metrics_row = mrow
        rv.addWidget(c4)

        root.addWidget(right, 1)

    def _slider_row(self, layout, label: str, lo: int, hi: int, val: int,
                    suffix: str = "", scale: int = 1):
        row = QHBoxLayout()
        lb = QLabel(label)
        lb.setFixedWidth(78)
        row.addWidget(lb)
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(val)
        row.addWidget(sl, 1)

        def fmt(v: int) -> str:
            return f"{v / scale:.2f}{suffix}" if scale > 1 else f"{v}{suffix}"

        vl = QLabel(fmt(val))
        vl.setFixedWidth(52)
        vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        vl.setProperty("role", "muted")
        row.addWidget(vl)
        layout.addLayout(row)
        sl.valueChanged.connect(lambda v: vl.setText(fmt(v)))
        return sl, vl

    # ------------------------------------------------------------------ #
    def refresh_voices(self) -> None:
        cur = self.cmb_voice.currentData()
        self.cmb_voice.blockSignals(True)
        self.cmb_voice.clear()
        voices = self.store.list()
        for p in voices:
            self.cmb_voice.addItem(f"{p.name}（{p.duration:.1f}s）", p.id)
        self.cmb_voice.blockSignals(False)

        last = str(CONFIG.get("last_voice") or "")
        idx = 0
        for i, p in enumerate(voices):
            if p.id == (cur or last):
                idx = i
                break
        if voices:
            self.cmb_voice.setCurrentIndex(idx)
            self._on_voice(idx)
        else:
            self.lb_voice.setText("音色库为空，请先到「音色库」导入素材")
            self.lb_voice.setStyleSheet(f"color: {theme.WARN};")

    def refresh_engines(self) -> None:
        cur = self.cmb_engine.currentData()
        self.cmb_engine.blockSignals(True)
        self.cmb_engine.clear()
        for e in all_engines():
            ok, _ = e.available()
            self.cmb_engine.addItem(e.label + ("" if ok else "（未安装）"), e.key)
        self.cmb_engine.blockSignals(False)

        target = cur or default_engine().key
        for i in range(self.cmb_engine.count()):
            if self.cmb_engine.itemData(i) == target:
                self.cmb_engine.setCurrentIndex(i)
                break
        self._on_engine(self.cmb_engine.currentIndex())

    def _on_voice(self, _idx: int) -> None:
        vid = self.cmb_voice.currentData()
        p = self.store.get(vid) if vid else None
        if p is None:
            return
        CONFIG.set("last_voice", p.id)
        has_text = bool(p.ref_text.strip())
        self.lb_voice.setText(
            f"{p.duration:.1f} 秒参考音频 · 质量 {p.quality} 分 · "
            + ("参考文本就绪" if has_text else "⚠ 缺少参考文本，需补填"))
        self.lb_voice.setStyleSheet("" if has_text else f"color: {theme.WARN};")

    def _on_engine(self, _idx: int) -> None:
        key = self.cmb_engine.currentData()
        e = get_engine(key) if key else None
        if e is None:
            return
        ok, msg = e.available()
        desc = e.description
        self.lb_desc.setText(desc if len(desc) <= 44 else desc[:44] + "…")
        self.lb_desc.setToolTip(desc)
        self.lb_engine.setText("状态：" + msg)
        self.lb_engine.setStyleSheet("" if ok else f"color: {theme.WARN};")
        self.cmb_voice.setEnabled(e.kind == "clone")
        is_f5 = e.key == "f5tts"
        self.sl_cfg.setEnabled(is_f5)
        self.sl_nfe.setEnabled(is_f5)

    def _reset_params(self) -> None:
        self.sl_speed.setValue(100)
        self.sl_cfg.setValue(200)
        self.sl_nfe.setValue(int(CONFIG.get("nfe_step") or 24))
        self.sp_gap.setValue(int(CONFIG.get("gap_ms") or 180))

    # ------------------------------------------------------------------ #
    def _on_text(self) -> None:
        n = len(self.txt.toPlainText().strip())
        self.lb_chars.setText(f"{n} 字")
        est = n / 4.2
        self.lb_len.setText(f"预计时长 ≈ {int(est // 60)}:{int(est % 60):02d}" if n else "")

    def _check_text(self) -> None:
        raw = self.txt.toPlainText().strip()
        if not raw:
            QMessageBox.information(self, "提示", "请先输入文本。")
            return
        TextCheckDialog(text_report(raw), self).exec()

    # ------------------------------------------------------------------ #
    def current_profile(self) -> Optional[VoiceProfile]:
        vid = self.cmb_voice.currentData()
        return self.store.get(vid) if vid else None

    def select_voice(self, profile: Optional[VoiceProfile]) -> None:
        if profile is None:
            return
        for i in range(self.cmb_voice.count()):
            if self.cmb_voice.itemData(i) == profile.id:
                self.cmb_voice.setCurrentIndex(i)
                self._on_voice(i)
                return

    def _run(self) -> None:
        raw = self.txt.toPlainText().strip()
        if not raw:
            QMessageBox.information(self, "提示", "请先输入要朗读的文本。")
            return
        key = self.cmb_engine.currentData()
        engine = get_engine(key) if key else default_engine()
        if engine is None:
            return
        ok, msg = engine.available()
        if not ok:
            QMessageBox.warning(
                self, "引擎不可用",
                f"{engine.label} 当前不可用：{msg}\n\n"
                "请到「设置」页面安装依赖，或切换到「系统语音 · 免模型」引擎试用完整流程。")
            return

        profile = self.current_profile()
        if engine.kind == "clone" and profile is None:
            QMessageBox.information(self, "提示", "请先创建并选择一个音色。")
            return
        if engine.kind == "clone" and profile is not None and not profile.ref_text.strip():
            QMessageBox.information(
                self, "缺少参考文本",
                "该音色还没有参考文本。请到「音色库」补填（或使用自动识别）后保存。")
            return

        out_dir = CONFIG.output_dir()
        name = (profile.name if profile else "tts").replace(" ", "_")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"{name}_{stamp}.wav"

        speed = self.sl_speed.value() / 100.0
        nfe = self.sl_nfe.value()
        cfg = self.sl_cfg.value() / 100.0
        gap = float(self.sp_gap.value())

        def job(emit, is_cancelled):
            return synthesize(
                raw, profile, engine, out_path,
                speed=speed, nfe=nfe, cfg=cfg, gap_ms=gap,
                progress_cb=lambda p, m: emit(p, m),
                cancel_cb=is_cancelled,
            )

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.bar.setValue(0)
        self.player.setVisible(False)
        for w in (self.m_dur, self.m_cost, self.m_chunks, self.m_engine):
            w.set_value("—")

        w = Worker(job, self)
        self._worker = w
        w.progressed.connect(self._on_progress)
        w.succeeded.connect(self._on_done)
        w.failed.connect(self._on_fail)
        w.cancelled.connect(lambda: self._finish_state("已取消"))
        w.finished.connect(w.deleteLater)
        self._t0 = time.time()
        self._last_msg = "正在准备"
        self._timer.start()
        w.start()
        self.statusMessage.emit("开始合成…")

    def _on_progress(self, pct: int, msg: str) -> None:
        self.bar.setValue(pct)
        self._last_msg = msg
        self.lb_state.setText(msg)

    def _tick(self) -> None:
        if not self._t0:
            return
        self.lb_state.setText(f"{self._last_msg} · 已用时 {int(time.time() - self._t0)} 秒")

    def _on_done(self, res: SynthResult) -> None:
        self._last = res
        self.bar.setValue(100)
        self.lb_state.setText(f"完成：{res.wav.name}")
        self.player.setVisible(True)
        self.player.load(res.wav)
        self.m_dur.set_value(f"{res.duration:.1f}s")
        self.m_cost.set_value(f"{res.elapsed:.0f}s")
        self.m_chunks.set_value(str(res.chunks))
        self.m_engine.set_value(res.engine.split("·")[0].strip())
        self._finish_state("合成完成")
        self.statusMessage.emit(f"已生成：{res.wav}")
        if CONFIG.get("open_after_synth"):
            self.player.load(res.wav, autoplay=True)

    def _on_fail(self, msg: str) -> None:
        self.bar.setValue(0)
        self.lb_state.setText("合成失败")
        self._finish_state("合成失败")
        QMessageBox.critical(self, "合成失败", msg.split("\n")[0])

    def _finish_state(self, msg: str) -> None:
        self._timer.stop()
        self._worker = None
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lb_state.setText(msg)

    def _stop(self) -> None:
        try:
            if self._worker is not None and self._worker.isRunning():
                self._worker.cancel()
                self.lb_state.setText("正在停止…（当前段完成后中断）")
        except RuntimeError:
            self._worker = None
