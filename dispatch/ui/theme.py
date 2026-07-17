"""
Dark theme.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

BG = "#16181d"
BG_ALT = "#1c1f26"
BG_RAISED = "#22262f"
BORDER = "#2f3540"
TEXT = "#dfe3ea"
TEXT_DIM = "#8b93a1"
ACCENT = "#22b8cf"
ACCENT_DIM = "#16697d"
WARN = "#e8a33d"
DANGER = "#e05260"
OK = "#4caf7d"

CATEGORY_COLORS = {
    "ransomware": "#e05260",
    "vulnerability": "#e8a33d",
    "breach": "#c678dd",
    "malware": "#e07a5f",
    "apt": "#61afef",
    "policy": "#4caf7d",
    "research": "#56b6c2",
    "other": "#8b93a1",
}

STATUS_COLORS = {
    "new": TEXT,
    "starred": "#e8a33d",
    "posted": OK,
    "killed": TEXT_DIM,
}

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}

QToolBar {{
    background: {BG_ALT};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 4px 6px;
    spacing: 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 10px;
    color: {TEXT};
}}
QToolBar QToolButton:hover {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
}}
QToolBar QToolButton:pressed {{ background: {ACCENT_DIM}; }}
QToolBar QToolButton:disabled {{ color: {TEXT_DIM}; }}

QMenuBar {{ background: {BG_ALT}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {BG_RAISED}; }}
QMenu {{ background: {BG_ALT}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 12px; border-radius: 3px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QTreeWidget, QTableWidget, QListWidget {{
    background: {BG_ALT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    alternate-background-color: {BG};
    outline: none;
}}
QTreeWidget::item, QListWidget::item {{ padding: 5px 4px; border-radius: 3px; }}
QTableWidget::item {{ padding: 4px; }}
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
    background: {ACCENT_DIM};
    color: #ffffff;
}}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {BG_RAISED}; }}
QTreeWidget::branch {{ background: {BG_ALT}; }}

QHeaderView::section {{
    background: {BG_RAISED};
    color: {TEXT_DIM};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 6px 6px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {BG_RAISED}; border: none; }}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 7px;
    selection-background-color: {ACCENT_DIM};
    selection-color: #ffffff;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
}}

QPushButton {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ border: 1px solid {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_DIM}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {BORDER}; }}
QPushButton#primary {{
    background: {ACCENT_DIM};
    border: 1px solid {ACCENT};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT}; }}
QPushButton#danger:hover {{ border: 1px solid {DANGER}; color: {DANGER}; }}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 5px;
    top: -1px;
}}
QTabBar::tab {{
    background: {BG};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {BG_ALT};
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

QStatusBar {{
    background: {BG_ALT};
    border-top: 1px solid {BORDER};
    color: {TEXT_DIM};
}}
QStatusBar::item {{ border: none; }}

QProgressBar {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: 3px;
    text-align: center;
    color: {TEXT};
    max-height: 14px;
}}
QProgressBar::chunk {{ background: {ACCENT_DIM}; border-radius: 2px; }}

QScrollBar:vertical {{
    background: {BG};
    width: 11px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 26px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_DIM}; }}
QScrollBar:horizontal {{ background: {BG}; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 26px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QLabel#hint {{ color: {TEXT_DIM}; }}
QLabel#heading {{ font-size: 15px; font-weight: 600; }}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {BG_RAISED};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QToolTip {{
    background: {BG_RAISED};
    color: {TEXT};
    border: 1px solid {ACCENT_DIM};
    padding: 4px;
}}
"""
