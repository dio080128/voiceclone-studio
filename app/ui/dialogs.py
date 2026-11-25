# -*- coding: utf-8 -*-
"""对话框：新建音色、文本检查、引擎安装。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox,
                               QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea,
                               QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..core import asr
from ..core.audio_proc import (AUDIO_EXTS, PreprocessOptions, build_reference,
                               read_audio)
from ..core.profiles import VoiceProfile, VoiceStore
from ..core.textnorm import analyze
from . import theme
from .widgets import Card, HLine, MetricBox, PlayerBar, chip, muted, title
from .worker import Worker


# --------------------------------------------------------------------------- #
# 新建音色
# --------------------------------------------------------------------------- #

class NewVoiceDialog(QDialog):
    """导入音频素材 -> 自动预处理 -> 生成音色档案。"""

    def __init__(self, store: VoiceStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("新建音色 · 导入素材")
        # 按屏幕自适应：1366×768 这类小屏也要完整可见（内容区可滚动）
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(940, screen.width() - 60), min(830, screen.height() - 60))
        self.setMinimumSize(min(880, screen.width() - 40), min(520, screen.height() - 90))
        self.setStyleSheet(theme.stylesheet())

        self._files: List[Path] = []
        self._ref_wav: Optional[Path] = None
        self._quality = None
        self._reports = []
        self._worker: Optional[Worker] = None
        self.created: Optional[VoiceProfile] = None

        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 内容区可滚动：1366x768 这类小屏也能完整操作
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        body = QVBoxLayout(inner)
        body.setContentsMargins(20, 14, 20, 6)
        body.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        head = QHBoxLayout()
        head.addWidget(title("新建音色"))
        head.addStretch(1)
        steps = muted("① 导入素材 → ② 自动清洗 → ③ 填写文本")
        steps.setWordWrap(False)
        head.addWidget(steps)
        body.addLayout(head)

        # --- 素材 -------------------------------------------------------
        card1 = Card()
        row = QHBoxLayout()
        self.btn_files = QPushButton("添加音频文件")
        self.btn_dir = QPushButton("添加整个文件夹")
        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.setProperty("kind", "ghost")
        row.addWidget(self.btn_files)
        row.addWidget(self.btn_dir)
        row.addWidget(self.btn_clear)
        row.addStretch(1)
        self.file_count = muted("未选择素材")
        row.addWidget(self.file_count)
        card1.body.addLayout(row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["文件", "时长", "采样率", "质量", "说明"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(120)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        card1.body.addWidget(self.table)
        card1.body.addWidget(muted(
            "提示：素材越干净、越长（5~15 秒连贯说话）效果越好；"
            "可一次导入多条，软件会自动挑出最适合的一条作为音色参考。", tiny=True))
        body.addWidget(card1)

        # --- 选项 -------------------------------------------------------
        card2 = Card()
        card2.body.addWidget(title("预处理选项", 2))
        opt_row = QHBoxLayout()
        self.cb_trim = QCheckBox("裁剪首尾静音")
        self.cb_trim.setChecked(True)
        self.cb_norm = QCheckBox("响度归一")
        self.cb_norm.setChecked(True)
        self.cb_denoise = QCheckBox("背景降噪")
        self.cb_pick = QCheckBox("自动截取最佳片段")
        self.cb_pick.setChecked(True)
        for w in (self.cb_trim, self.cb_norm, self.cb_denoise, self.cb_pick):
            opt_row.addWidget(w)
        opt_row.addStretch(1)
        card2.body.addLayout(opt_row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("参考音频最长"))
        self.sp_max = QSpinBox()
        self.sp_max.setRange(5, 60)
        self.sp_max.setValue(12)
        self.sp_max.setSuffix(" 秒")
        self.sp_max.setFixedWidth(96)
        row2.addWidget(self.sp_max)
        row2.addStretch(1)
        self.btn_analyze = QPushButton("开始分析与预处理")
        self.btn_analyze.setProperty("kind", "primary")
        self.btn_analyze.setEnabled(False)
        row2.addWidget(self.btn_analyze)
        card2.body.addLayout(row2)
        body.addWidget(card2)

        # --- 预览 -------------------------------------------------------
        card3 = Card()
        self.lbl_preview = title("音色预览", 2)
        card3.body.addWidget(self.lbl_preview)
        self.player = PlayerBar(show_open=False)
        card3.body.addWidget(self.player)
        mrow = QHBoxLayout()
        self.m_dur = MetricBox("时长", "—")
        self.m_sr = MetricBox("采样率", "—")
        self.m_q = MetricBox("质量评分", "—")
        self.m_snr = MetricBox("信噪比", "—")
        for w in (self.m_dur, self.m_sr, self.m_q, self.m_snr):
            mrow.addWidget(w)
        card3.body.addLayout(mrow)
        body.addWidget(card3)

        # --- 文本与命名 --------------------------------------------------
        card4 = Card()
        card4.body.addWidget(title("参考文本", 2))
        card4.body.addWidget(muted(
            "请填写参考音频中“实际说的话”，须与音频内容完全一致，"
            "模型靠它对齐发音。可点右侧按钮自动识别。", tiny=True))
        self.txt_ref = QPlainTextEdit()
        self.txt_ref.setPlaceholderText("例如：大家好，我是小明，今天想和你聊聊声音克隆这件事。")
        self.txt_ref.setFixedHeight(70)
        card4.body.addWidget(self.txt_ref)

        rrow = QHBoxLayout()
        self.btn_asr = QPushButton("自动识别这段话")
        self.btn_asr.setProperty("kind", "ghost")
        self.lbl_asr = muted("")
        rrow.addWidget(self.btn_asr)
        rrow.addWidget(self.lbl_asr)
        rrow.addStretch(1)
        self.lbl_chars = muted("0 字")
        rrow.addWidget(self.lbl_chars)
        card4.body.addLayout(rrow)

        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("音色名称"))
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("给这个音色起个名字")
        nrow.addWidget(self.ed_name, 1)
        card4.body.addLayout(nrow)
        body.addWidget(card4)

        # --- 进度与按钮（固定在底部，不随内容滚动）------------------------
        footer = QWidget()
        fv = QVBoxLayout(footer)
        fv.setContentsMargins(20, 6, 20, 16)
        fv.setSpacing(8)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        fv.addWidget(self.progress)
        self.status = muted("")
        fv.addWidget(self.status)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_create = QPushButton("创建音色")
        self.btn_create.setProperty("kind", "primary")
        self.btn_create.setEnabled(False)
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_create)
        fv.addLayout(bottom)
        outer.addWidget(footer)

        # --- 连接 --------------------------------------------------------
        self.btn_files.clicked.connect(self._pick_files)
        self.btn_dir.clicked.connect(self._pick_dir)
        self.btn_clear.clicked.connect(self._clear_files)
        self.btn_analyze.clicked.connect(self._analyze)
        self.btn_asr.clicked.connect(self._transcribe)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_create.clicked.connect(self._create)
        self.txt_ref.textChanged.connect(self._update_chars)

    # ------------------------------------------------------------------ #
    def _update_chars(self) -> None:
        n = len(self.txt_ref.toPlainText().strip())
        self.lbl_chars.setText(f"{n} 字")
        self._refresh_create_btn()

    def _refresh_create_btn(self) -> None:
        ok = (self._ref_wav is not None
              and bool(self.ed_name.text().strip())
              and len(self.txt_ref.toPlainText().strip()) >= 4)
        self.btn_create.setEnabled(ok)

    def _pick_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频素材", "", f"音频文件 ({exts});;所有文件 (*.*)")
        if files:
            self._add([Path(f) for f in files])

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择素材文件夹")
        if not d:
            return
        files = [p for p in Path(d).rglob("*") if p.suffix.lower() in AUDIO_EXTS]
        if not files:
            QMessageBox.information(self, "提示", "该文件夹里没有找到音频文件。")
            return
        self._add(files[:80])

    def _add(self, files: List[Path]) -> None:
        for f in files:
            if f not in self._files:
                self._files.append(f)
        self._refresh_table_raw()
        self.btn_analyze.setEnabled(bool(self._files))
        self.file_count.setText(f"已选择 {len(self._files)} 个素材")

    def _clear_files(self) -> None:
        self._files.clear()
        self.table.setRowCount(0)
        self.file_count.setText("未选择素材")
        self.btn_analyze.setEnabled(False)

    def _refresh_table_raw(self) -> None:
        self.table.setRowCount(len(self._files))
        for i, f in enumerate(self._files):
            self.table.setItem(i, 0, QTableWidgetItem(f.name))
            self.table.setItem(i, 1, QTableWidgetItem("…"))
            self.table.setItem(i, 2, QTableWidgetItem("…"))
            self.table.setItem(i, 3, QTableWidgetItem("…"))
            self.table.setItem(i, 4, QTableWidgetItem("待分析"))

    # ------------------------------------------------------------------ #
    def _analyze(self) -> None:
        if not self._files:
            return
        opt = PreprocessOptions(
            trim=self.cb_trim.isChecked(),
            normalize=self.cb_norm.isChecked(),
            denoise=self.cb_denoise.isChecked(),
            auto_pick=self.cb_pick.isChecked(),
            max_sec=float(self.sp_max.value()),
            min_sec=min(4.0, float(self.sp_max.value())),
        )
        files = list(self._files)

        def job(emit, is_cancelled):
            emit(2, "正在读取与清洗素材…")
            import tempfile
            tmp = Path(tempfile.mkdtemp(prefix="vcs_new_")) / "reference.wav"
            ref, quality, reports = build_reference(files, tmp, opt)
            return ref, quality, reports

        self._run_worker(job, on_ok=self._on_analyzed, busy_widgets=[self.btn_analyze])

    def _on_analyzed(self, result) -> None:
        ref, quality, reports = result
        self._ref_wav = Path(ref)
        self._quality = quality
        self._reports = reports

        # 回填表格
        self.table.setRowCount(len(reports))
        for i, (path, q) in enumerate(reports):
            self.table.setItem(i, 0, QTableWidgetItem(Path(path).name))
            self.table.setItem(i, 1, QTableWidgetItem(f"{q.duration:.1f}s"))
            self.table.setItem(i, 2, QTableWidgetItem(f"{q.sr / 1000:.1f}k"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{q.score} · {q.verdict}"))
            note = "；".join(q.issues) if q.issues else "干净可用"
            if q.selected:
                note = "★ 已选为参考 · " + note
            self.table.setItem(i, 4, QTableWidgetItem(note))

        # 预览指标
        self.m_dur.set_value(f"{quality.duration:.1f}s")
        self.m_sr.set_value(f"{quality.sr / 1000:.1f} kHz")
        color = theme.OK if quality.score >= 80 else (theme.WARN if quality.score >= 55 else theme.DANGER)
        self.m_q.set_value(f"{quality.score}", color)
        self.m_snr.set_value(f"{quality.snr_db:.0f} dB")
        self.player.load(self._ref_wav)
        self.lbl_preview.setText(f"音色预览 · {quality.verdict}")
        self.status.setText("预处理完成，请填写参考文本后创建。")
        if not self.ed_name.text().strip():
            self.ed_name.setText(f"我的音色 {len(self.store.list()) + 1}")
        self._refresh_create_btn()

    # ------------------------------------------------------------------ #
    def _transcribe(self) -> None:
        if self._ref_wav is None:
            QMessageBox.information(self, "提示", "请先点击「开始分析与预处理」。")
            return
        ok, msg = asr.available()
        if not ok:
            QMessageBox.warning(
                self, "需要安装组件",
                "自动识别需要 faster-whisper。\n\n请在「设置 → 组件安装」中安装，"
                "或直接在下方手动输入参考文本。")
            return

        wav = self._ref_wav

        def job(emit, is_cancelled):
            return asr.transcribe(wav, progress=lambda m: emit(40, m))

        def done(text: str) -> None:
            self.txt_ref.setPlainText(text)
            self.lbl_asr.setText("识别完成，请核对是否与音频一致")

        self._run_worker(job, on_ok=done, busy_widgets=[self.btn_asr])

    # ------------------------------------------------------------------ #
    def _create(self) -> None:
        if self._ref_wav is None:
            return
        try:
            profile = self.store.create(
                name=self.ed_name.text().strip(),
                ref_wav=self._ref_wav,
                ref_text=self.txt_ref.toPlainText().strip(),
                quality=self._quality.score if self._quality else 0,
            )
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", str(exc))
            return
        self.created = profile
        self.accept()

    # ------------------------------------------------------------------ #
    def _run_worker(self, job, on_ok, busy_widgets=()) -> None:
        for w in busy_widgets:
            w.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status.setText("处理中…")

        w = Worker(job, self)
        self._worker = w

        def _progress(p, m):
            self.progress.setValue(max(0, min(100, p)))
            self.status.setText(m)

        def _done(res):
            self.progress.setVisible(False)
            for wid in busy_widgets:
                wid.setEnabled(True)
            try:
                on_ok(res)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "出错", str(exc))

        def _fail(msg: str):
            self.progress.setVisible(False)
            for wid in busy_widgets:
                wid.setEnabled(True)
            self.status.setText("处理失败")
            first = msg.split("\n")[0]
            # 完整堆栈写日志，弹窗里折叠显示，避免只剩一行没有上下文
            try:
                import datetime
                from ...core.config import LOGS_DIR
                LOGS_DIR.mkdir(parents=True, exist_ok=True)
                with open(LOGS_DIR / "error.log", "a", encoding="utf-8") as f:
                    f.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n{msg}\n")
            except Exception:
                pass
            box = QMessageBox(QMessageBox.Critical, "处理失败", first,
                              QMessageBox.Ok, self)
            # 多行消息通常是引擎给的诊断（比如内存不足），前几行就是结论，
            # 直接摊在弹窗里；堆栈仍折叠进「显示详细信息」，不占地方。
            extra = "\n".join(ln for ln in msg.split("\n")[1:] if ln.strip())[:420]
            if extra:
                box.setInformativeText(extra.rstrip() + "\n\n（完整内容点「显示详细信息」）")
            else:
                box.setInformativeText(
                    "常见原因：音频格式不受支持、文件损坏，或素材里没有可用的语音。\n"
                    "如果反复出现，请点「显示详细信息」把内容发给开发者。")
            box.setDetailedText(msg)
            box.exec()

        w.progressed.connect(_progress)
        w.succeeded.connect(_done)
        w.failed.connect(_fail)
        w.finished.connect(w.deleteLater)
        w.start()

    def reject(self) -> None:  # noqa: D102
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
        super().reject()


# --------------------------------------------------------------------------- #
# 文本检查
# --------------------------------------------------------------------------- #

class TextCheckDialog(QDialog):
    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("文本检查 · Unicode 覆盖与切句预览")
        self.setMinimumSize(760, 620)
        self.setStyleSheet(theme.stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addWidget(title("文本检查"))
        root.addWidget(muted(report["stats"].summary()))

        root.addWidget(QLabel("规范化后的朗读文本（引擎实际接收的内容）"))
        box1 = QPlainTextEdit(report["normalized"])
        box1.setReadOnly(True)
        box1.setFixedHeight(150)
        root.addWidget(box1)

        root.addWidget(QLabel(f"切句结果（共 {len(report['chunks'])} 段，逐段合成后拼接）"))
        box2 = QPlainTextEdit("\n".join(
            f"{i + 1:>2}. {c}" for i, c in enumerate(report["chunks"])))
        box2.setReadOnly(True)
        root.addWidget(box2, 1)

        unsupported = report.get("unsupported") or []
        if unsupported:
            lb = QLabel("⚠ 以下字符可能无法朗读，建议替换：" + " ".join(unsupported[:40]))
            lb.setWordWrap(True)
            lb.setStyleSheet(f"color: {theme.WARN};")
            root.addWidget(lb)

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("关闭")
        btn.setProperty("kind", "primary")
        btn.clicked.connect(self.accept)
        row.addWidget(btn)
        root.addLayout(row)


# --------------------------------------------------------------------------- #
# 组件安装
# --------------------------------------------------------------------------- #

class InstallDialog(QDialog):
    """用 pip 安装引擎依赖，实时显示日志。"""

    def __init__(self, packages: List[str], title_text: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.packages = packages
        self.setWindowTitle("组件安装")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(theme.stylesheet())
        self._proc: Optional[QProcess] = None
        self.success = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addWidget(title(title_text))
        root.addWidget(muted("将执行：" + " ".join(packages) + "　（首次安装需数百 MB 下载，请耐心等待）"))

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        root.addWidget(self.log, 1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # 不确定进度
        root.addWidget(self.bar)

        row = QHBoxLayout()
        self.status = muted("准备中…")
        row.addWidget(self.status, 1)
        self.btn_close = QPushButton("关闭")
        row.addWidget(self.btn_close)
        root.addLayout(row)

        self.btn_close.clicked.connect(self._on_close)
        QTimer.singleShot(200, self._start)

    def _start(self) -> None:
        if not self.packages:
            # 没有包名时 pip 会直接报错退出，这里提前收尾，别留下一条失败日志。
            self.bar.setRange(0, 1)
            self.bar.setValue(0)
            self.status.setText("没有需要安装的依赖")
            self._append("[跳过] 依赖清单为空，未执行 pip。")
            return
        py = sys.executable
        self._append(f"> {py} -m pip install -U " + " ".join(self.packages))
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self._read)
        p.finished.connect(self._finished)
        p.setProgram(py)
        p.setArguments(["-m", "pip", "install", "-U", "--no-input", *self.packages])
        env = p.processEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        p.setProcessEnvironment(env)
        self._proc = p
        p.start()
        self.status.setText("正在安装…")

    def _read(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._append(data.rstrip())

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _finished(self, code: int, _status) -> None:
        self.bar.setRange(0, 1)
        self.bar.setValue(1 if code == 0 else 0)
        self.success = code == 0
        self.status.setText("安装成功，返回上一页并重启软件即可使用。" if code == 0
                            else f"安装失败（退出码 {code}），请检查网络或手动安装。")
        self.status.setProperty("role", "muted")
        self._append("\n[完成] " + ("成功" if code == 0 else f"失败，退出码 {code}"))

    def _on_close(self) -> None:
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            self._proc.kill()
        self.accept()
