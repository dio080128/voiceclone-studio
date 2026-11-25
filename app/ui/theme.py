# -*- coding: utf-8 -*-
"""浅色主题配色与全局样式表。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtCore import Qt, QRectF

BG = "#F4F6F9"
PANEL = "#FFFFFF"
PANEL_ALT = "#FAFBFC"
BORDER = "#E3E7ED"
BORDER_STRONG = "#CFD6E0"
TEXT = "#1E2430"
MUTED = "#6B7480"
ACCENT = "#2E6BE6"
ACCENT_HOVER = "#2158C8"
ACCENT_SOFT = "#EBF1FE"
OK = "#16A34A"
WARN = "#D97706"
DANGER = "#D64545"

FONT_FAMILY = "Microsoft YaHei UI"


def app_font(size: int = 10) -> QFont:
    f = QFont(FONT_FAMILY, size)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def stylesheet() -> str:
    return f"""
* {{
    font-family: "{FONT_FAMILY}";
    outline: none;
}}
QWidget {{
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QWidget#Root {{
    background: {BG};
}}
QFrame#Sidebar {{
    background: {PANEL};
    border-right: 1px solid {BORDER};
}}
QFrame#Card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#CardFlat {{
    background: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#SponsorChip {{
    background: {ACCENT_SOFT};
    border: 1px solid #D6E2FB;
    border-radius: 8px;
}}
QLabel[role="h1"] {{
    font-size: 19px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel[role="h2"] {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel[role="muted"] {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel[role="tiny"] {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel[role="brand"] {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel[role="chip"] {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
}}
QLabel[role="chipOk"] {{
    background: #E7F7EE; color: {OK};
    border-radius: 9px; padding: 2px 9px; font-size: 11px;
}}
QLabel[role="chipWarn"] {{
    background: #FEF3E2; color: {WARN};
    border-radius: 9px; padding: 2px 9px; font-size: 11px;
}}
QLabel[role="chipBad"] {{
    background: #FDECEC; color: {DANGER};
    border-radius: 9px; padding: 2px 9px; font-size: 11px;
}}

QPushButton {{
    background: {PANEL};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 7px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    background: #F7F9FC;
    border-color: #B9C2CF;
}}
QPushButton:pressed {{
    background: #EEF1F6;
}}
QPushButton:disabled {{
    color: #A8AFB9;
    background: #F3F5F8;
    border-color: {BORDER};
}}
QPushButton[kind="primary"] {{
    background: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
    font-weight: 600;
    padding: 8px 18px;
}}
QPushButton[kind="primary"]:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton[kind="primary"]:disabled {{
    background: #A9BFF0;
    border-color: #A9BFF0;
    color: #F4F7FF;
}}
QPushButton[kind="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {ACCENT};
    padding: 6px 10px;
}}
QPushButton[kind="ghost"]:hover {{
    background: {ACCENT_SOFT};
}}
QPushButton[kind="danger"] {{
    color: {DANGER};
    border-color: #F0C4C4;
    background: #FDF5F5;
}}
QPushButton[kind="nav"] {{
    text-align: left;
    padding: 9px 14px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: #3C4552;
    font-size: 13px;
}}
QPushButton[kind="nav"]:hover {{
    background: #F2F5FA;
}}
QPushButton[kind="navActive"] {{
    text-align: left;
    padding: 9px 14px;
    border: none;
    border-radius: 8px;
    background: {ACCENT_SOFT};
    color: {ACCENT};
    font-weight: 600;
    font-size: 13px;
}}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {PANEL};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT};
    padding: 4px;
    outline: none;
}}

QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-radius: 9px;
    margin: 2px 2px;
    padding: 0px;
}}
QListWidget::item:selected {{
    background: {ACCENT_SOFT};
}}
QListWidget::item:hover {{
    background: #F5F7FB;
}}

QTableWidget {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: #F0F2F6;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: {PANEL_ALT};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 7px 8px;
    font-size: 12px;
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: #E2E6EC;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    margin: -6px 0;
    border-radius: 7px;
    background: white;
    border: 1px solid {ACCENT};
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_SOFT};
}}

QProgressBar {{
    background: #E9EDF3;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}

QCheckBox {{
    spacing: 7px;
    color: {TEXT};
}}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border-radius: 4px;
    border: 1px solid {BORDER_STRONG};
    background: white;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QRadioButton {{
    spacing: 6px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #CDD4DE;
    border-radius: 4px;
    min-height: 26px;
}}
QScrollBar::handle:vertical:hover {{
    background: #B6BFCC;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #CDD4DE;
    border-radius: 4px;
    min-width: 26px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QStatusBar {{
    background: {PANEL};
    border-top: 1px solid {BORDER};
    color: {MUTED};
    font-size: 12px;
}}
QSplitter::handle {{
    background: transparent;
}}
QToolTip {{
    background: #2B3240;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 5px 8px;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {MUTED};
    font-size: 12px;
}}
"""


def make_app_icon(size: int = 128) -> QIcon:
    """用代码绘制一枚声波图标，省去外部资源依赖。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)

    bars = [0.26, 0.46, 0.72, 0.94, 0.72, 0.46, 0.26]
    p.setBrush(QColor("#FFFFFF"))
    bw = size * 0.075
    gap = size * 0.038
    total = len(bars) * bw + (len(bars) - 1) * gap
    x = (size - total) / 2
    for h in bars:
        bh = size * 0.52 * h
        p.drawRoundedRect(QRectF(x, (size - bh) / 2, bw, bh), bw / 2, bw / 2)
        x += bw + gap
    p.end()
    return QIcon(pm)
