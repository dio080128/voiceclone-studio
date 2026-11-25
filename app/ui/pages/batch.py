# -*- coding: utf-8 -*-
"""批量合成页面：一次生成多条文本。"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ...core.config import CONFIG
from ...core.engines.registry import all_engines, default_engine, get_engine
from ...core.profiles import VoiceStore
from ...core.synth import synthesize
from .. import theme
from ..widgets import Card, muted, title
from ..worker import Worker


class BatchPage(QWidget):
    statusMessage = Signal(str)
    rowUpdate = Signal(int, str, str, str)   # 行号, 状态, 文件, 时长

    def __init__(self, store: VoiceStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._worker: Optional[Worker] = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        c1 = Card()
        head = QHBoxLayout()
        head.addWidget(title("批量合成"))
        head.addStretch(1)
        self.btn_import = QPushButton("导入文本文件（每行一条）")
        self.btn_import.clicked.connect(self._import)
        head.addWidget(self.btn_import)
        c1.body.addLayout(head)
        c1.body.addWidget(muted(
            "每行文本会生成一个音频文件，按序号命名。支持 txt / csv（取第一列）。"
            "适合做有声书、课程音频、提示音库。", tiny=True))

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("音色"))
        self.cmb_voice = QComboBox()
        self.cmb_voice.setMinimumWidth(180)
        row.addWidget(self.cmb_voice)
        row.addWidget(QLabel("引擎"))
        self.cmb_engine = QComboBox()
        self.cmb_engine.setMinimumWidth(170)
        row.addWidget(self.cmb_engine)
        row.addWidget(QLabel("输出目录"))
        self.ed_out = QLineEdit(str(CONFIG.output_dir()))
        row.addWidget(self.ed_out, 1)
        self.btn_dir = QPushButton("选择")
        self.btn_dir.clicked.connect(self._pick_dir)
        row.addWidget(self.btn_dir)
        c1.body.addLayout(row)
        root.addWidget(c1)

        c2 = Card()
        c2.body.addWidget(QLabel("待合成文本（每行一条）"))
        self.txt = QPlainTextEdit()
        self.txt.setMinimumHeight(110)
        self.txt.setPlaceholderText("第一条：欢迎使用声纹工坊。\n"
                                    "第二条：今天是 2026 年 11 月 9 日。\n"
                                    "第三条：Hello world, this is a cloned voice.")
        c2.body.addWidget(self.txt, 1)
        c2.setMinimumHeight(250)

        bar = QHBoxLayout()
        self.btn_run = QPushButton("开始批量合成")
        self.btn_run.setProperty("kind", "primary")
        self.btn_run.clicked.connect(self._run)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        bar.addWidget(self.btn_run)
        bar.addWidget(self.btn_stop)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        bar.addWidget(self.bar, 1)
        self.lb_state = muted("准备就绪")
        bar.addWidget(self.lb_state)
        c2.body.addLayout(bar)
        root.addWidget(c2, 1)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "文本", "状态", "时长", "文件"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMaximumHeight(200)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 46)
        for c in (2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        root.addWidget(self.table)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_open = QPushButton("打开输出目录")
        self.btn_open.setProperty("kind", "ghost")
        self.btn_open.clicked.connect(self._open_out)
        bottom.addWidget(self.btn_open)
        root.addLayout(bottom)

        self.rowUpdate.connect(self._on_row)

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self.cmb_voice.clear()
        for p in self.store.list():
            self.cmb_voice.addItem(p.name, p.id)
        cur = self.cmb_engine.currentData()
        self.cmb_engine.clear()
        for e in all_engines():
            ok, _ = e.available()
            self.cmb_engine.addItem(e.label + ("" if ok else "（未安装）"), e.key)
        target = cur or default_engine().key
        for i in range(self.cmb_engine.count()):
            if self.cmb_engine.itemData(i) == target:
                self.cmb_engine.setCurrentIndex(i)
                break

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.ed_out.text())
        if d:
            self.ed_out.setText(d)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择文本文件", "", "文本文件 (*.txt *.csv *.md);;所有文件 (*.*)")
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            QMessageBox.warning(self, "读取失败", str(exc))
            return
        lines = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if path.lower().endswith(".csv") and "," in line:
                line = line.split(",")[0].strip().strip('"')
            if line:
                lines.append(line)
        self.txt.setPlainText("\n".join(lines))
        self.statusMessage.emit(f"已导入 {len(lines)} 条文本")

    def _open_out(self) -> None:
        import os
        d = Path(self.ed_out.text() or CONFIG.output_dir())
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(d))  # type: ignore[attr-defined]
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        lines = [l.strip() for l in self.txt.toPlainText().splitlines() if l.strip()]
        if not lines:
            QMessageBox.information(self, "提示", "请先输入或导入文本。")
            return
        key = self.cmb_engine.currentData()
        engine = get_engine(key) if key else default_engine()
        if engine is None:
            return
        ok, msg = engine.available()
        if not ok:
            QMessageBox.warning(self, "引擎不可用", f"{engine.label}：{msg}")
            return

        profile = self.store.get(self.cmb_voice.currentData()) if self.cmb_voice.currentData() else None
        if engine.kind == "clone":
            if profile is None:
                QMessageBox.information(self, "提示", "请先选择音色。")
                return
            if not profile.ref_text.strip():
                QMessageBox.information(self, "提示", "该音色缺少参考文本，无法克隆。")
                return

        out_dir = Path(self.ed_out.text() or CONFIG.output_dir())
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        speed = 1.0
        nfe = int(CONFIG.get("nfe_step") or 24)
        cfg = float(CONFIG.get("cfg_strength") or 2.0)

        self.table.setRowCount(len(lines))
        for i, text in enumerate(lines):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            item = QTableWidgetItem(text[:60])
            item.setToolTip(text)
            self.table.setItem(i, 1, item)
            self.table.setItem(i, 2, QTableWidgetItem("等待"))
            self.table.setItem(i, 3, QTableWidgetItem("—"))
            self.table.setItem(i, 4, QTableWidgetItem(""))

        def job(emit, is_cancelled):
            done = 0
            for i, text in enumerate(lines):
                if is_cancelled():
                    raise InterruptedError
                emit(int(100 * i / len(lines)), f"第 {i + 1}/{len(lines)} 条：{text[:16]}…")
                self.rowUpdate.emit(i, "合成中", "", "")
                out = out_dir / f"{stamp}_{i + 1:03d}.wav"
                res = synthesize(text, profile, engine, out, speed=speed,
                                 nfe=nfe, cfg=cfg, cancel_cb=is_cancelled,
                                 progress_cb=None)
                self.rowUpdate.emit(i, "完成", str(res.wav), f"{res.duration:.1f}s")
                done += 1
            emit(100, f"全部完成，共 {done} 条")
            return done

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.bar.setValue(0)

        w = Worker(job, self)
        self._worker = w
        w.progressed.connect(lambda p, m: (self.bar.setValue(p), self.lb_state.setText(m)))
        w.succeeded.connect(lambda n: self._finish(f"完成 {n} 条"))
        w.failed.connect(self._fail)
        w.cancelled.connect(lambda: self._finish("已停止"))
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_row(self, row: int, status: str, path: str, dur: str) -> None:
        if row < self.table.rowCount():
            self.table.setItem(row, 2, QTableWidgetItem(status))
            if dur:
                self.table.setItem(row, 3, QTableWidgetItem(dur))
            if path:
                self.table.setItem(row, 4, QTableWidgetItem(Path(path).name))
            self.table.scrollToItem(self.table.item(row, 0))

    def _finish(self, msg: str) -> None:
        self._worker = None
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lb_state.setText(msg)
        self.statusMessage.emit(msg)

    def _fail(self, msg: str) -> None:
        self._finish("批量失败")
        QMessageBox.critical(self, "批量合成失败", msg.split("\n")[0])

    def _stop(self) -> None:
        try:
            if self._worker is not None and self._worker.isRunning():
                self._worker.cancel()
                self.lb_state.setText("正在停止…")
        except RuntimeError:
            self._worker = None
