# -*- coding: utf-8 -*-
"""界面截图工具（开发用）：启动主窗口并把每个页面渲染成 PNG。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import app_font, make_app_icon, stylesheet  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "cache" / "shots")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(app_font(10))
    app.setWindowIcon(make_app_icon())
    app.setStyleSheet(stylesheet())

    win = MainWindow()
    win.resize(1300, 880)
    win.show()

    pages = ["01_synth.png", "02_library.png", "03_batch.png", "04_settings.png"]

    def shoot() -> None:
        from app.ui.pages.synth import SAMPLE_TEXT
        win.synth_page.txt.setPlainText(SAMPLE_TEXT)
        for i, name in enumerate(pages):
            win._switch(i)
            app.processEvents()
            win.grab().save(str(OUT / name))
        app.quit()

    QTimer.singleShot(1500, shoot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
