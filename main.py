# -*- coding: utf-8 -*-
"""声纹工坊 · VoiceClone Studio 启动入口。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _log_dir() -> Path:
    home = os.environ.get("VCS_HOME", "").strip()
    base = Path(home) if home else ROOT
    d = base / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def _install_error_hook() -> None:
    """发行版用 pythonw 启动、没有控制台，异常必须落盘 + 弹窗。"""
    log_path = _log_dir() / "error.log"

    def hook(exc_type, exc, tb):
        import datetime
        import traceback
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n{text}")
        except Exception:
            pass
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None,
                f"程序遇到错误：\n{exc}\n\n详细信息已记录到：\n{log_path}",
                "声纹工坊 · 出错了", 0x00000010)
        except Exception:
            pass

    sys.excepthook = hook


def main() -> int:
    _install_error_hook()
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # 屏蔽 Qt 多媒体后端刷屏的 ffmpeg 信息
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg=false")

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow
    from app.ui.theme import app_font, make_app_icon, stylesheet

    try:  # Windows 任务栏图标分组
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "VoiceCloneStudio.App.1")
    except Exception:
        pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("声纹工坊")
    app.setApplicationDisplayName("声纹工坊 · VoiceClone Studio")
    app.setOrganizationName("VoiceCloneStudio")
    app.setFont(app_font(10))
    app.setWindowIcon(make_app_icon())
    app.setStyleSheet(stylesheet())

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
