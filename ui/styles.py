"""Existing application styles shared by the workspace shell."""

_STYLE = """
QMainWindow, QWidget { font-size: 11px; }

/* ── Group boxes ── */
QGroupBox {
    font-weight: bold;
    font-size: 11px;
    border: 1px solid #4a4a4a;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 8px;
    background: #2b2b2b;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #b8b8b8;
}

/* ── Input controls ── */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    padding: 2px 6px;
    min-height: 24px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #5b9bd5;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #4a4a4a;
    selection-background-color: #3a6ea5;
}

/* ── Standard buttons ── */
QPushButton {
    background: #3c3f41;
    color: #d4d4d4;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px 10px;
    min-height: 24px;
}
QPushButton:hover  { background: #4c5052; border-color: #6a6a6a; }
QPushButton:pressed { background: #2a2d2f; }
QPushButton:disabled { background: #2a2d2f; color: #555; border-color: #3a3a3a; }

/* ── Primary action buttons (plot buttons) – class applied in code ── */
QPushButton[class="primary"] {
    background: #2b5190;
    color: #e8eaf0;
    border: 1px solid #3a68b8;
    font-weight: bold;
}
QPushButton[class="primary"]:hover  { background: #3461a8; border-color: #4a7acc; }
QPushButton[class="primary"]:pressed { background: #1e3d6e; }
QPushButton[class="primary"]:disabled { background: #243650; color: #556; border-color: #2a3a50; }

/* ── Table ── */
QTableWidget {
    background: #1e1e1e;
    color: #e0e0e0;
    gridline-color: #3a3a3a;
    border: 1px solid #4a4a4a;
    border-radius: 3px;
}
QHeaderView::section {
    background: #2e3033;
    color: #b8b8b8;
    border: none;
    border-right: 1px solid #4a4a4a;
    border-bottom: 1px solid #4a4a4a;
    padding: 3px 5px;
    font-weight: bold;
}

/* ── Tab widget ── */
QTabWidget::pane {
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    background: #252525;
}
QTabBar::tab {
    background: #2b2b2b;
    color: #999;
    border: 1px solid #4a4a4a;
    border-bottom: none;
    padding: 5px 14px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
QTabBar::tab:selected { background: #323232; color: #ddd; border-bottom: none; }
QTabBar::tab:hover:!selected { background: #333; color: #bbb; }

/* ── Scrollbars ── */
QScrollBar:vertical {
    background: #1e1e1e;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #4a4a4a;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #5a5a5a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #1e1e1e;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #4a4a4a;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #5a5a5a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Splitter ── */
QSplitter::handle { background: #3a3a3a; }
QSplitter::handle:hover { background: #5b9bd5; }
"""


_LIGHT_STYLE = """
QMainWindow, QWidget {
    font-size: 11px;
    color: #1f2937;
    background: #f5f7fb;
}

QLabel {
    background: transparent;
}

QWidget#SidebarPanel,
QWidget#PreviewPanel,
QWidget#StatusPanel {
    background: #f5f7fb;
}

QFrame#StageCard,
QFrame#PanelCard {
    background: #ffffff;
    border: 1px solid #d9e2f2;
    border-radius: 6px;
}

QWidget[class="sectionContent"],
QWidget[class="inlineRow"] {
    background: transparent;
}

QToolButton[class="sectionToggle"] {
    background: transparent;
    border: none;
    color: #16324f;
    font-size: 12px;
    font-weight: 600;
    padding: 2px 6px;
    text-align: left;
}
QToolButton[class="sectionToggle"]:hover {
    color: #27496d;
}

QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #d3ddea;
    border-radius: 4px;
    padding: 2px 6px;
    min-height: 20px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #4f7edc;
}
QLineEdit:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {
    background: #f5f7fb;
    color: #748397;
    border-color: #dbe3ef;
}
QPushButton:focus, QToolButton:focus {
    border: 1px solid #4f7edc;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #d3ddea;
    selection-background-color: #dbeafe;
    selection-color: #16324f;
}

QPushButton {
    background: #ffffff;
    color: #27496d;
    border: 1px solid #d3ddea;
    border-radius: 5px;
    padding: 2px 8px;
    min-height: 20px;
    font-weight: 500;
}
QPushButton:hover {
    background: #f3f7ff;
    border-color: #b8c8e0;
}
QPushButton:pressed {
    background: #e7eefb;
}
QPushButton:disabled {
    background: #f5f7fb;
    color: #94a3b8;
    border-color: #dbe3ef;
}

QPushButton[class="primary"] {
    background: #3566c1;
    color: #ffffff;
    border: 1px solid #2f5aac;
    font-weight: 600;
}
QPushButton[class="primary"]:hover {
    background: #3d73d7;
    border-color: #3566c1;
}
QPushButton[class="primary"]:pressed {
    background: #2f5aac;
}
QPushButton[class="primary"]:disabled {
    background: #b8c9ea;
    color: #eff4fd;
    border-color: #b8c9ea;
}

QPushButton[class="ghost"] {
    background: #f8fbff;
    color: #35506b;
    border: 1px solid #d9e2f2;
}

QTableWidget {
    background: #ffffff;
    color: #1f2937;
    gridline-color: #e3eaf5;
    border: 1px solid #d3ddea;
    border-radius: 5px;
}
QHeaderView::section {
    background: #eef4fb;
    color: #35506b;
    border: none;
    border-right: 1px solid #d9e2f2;
    border-bottom: 1px solid #d9e2f2;
    padding: 6px 8px;
    font-weight: 600;
}

QTabWidget::pane {
    border: 1px solid #d9e2f2;
    border-radius: 6px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: #eef3fb;
    color: #5a7088;
    border: 1px solid #d9e2f2;
    border-bottom: none;
    padding: 4px 12px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #16324f;
}
QTabBar::tab:hover:!selected {
    background: #f5f8fe;
    color: #27496d;
}

QTextEdit {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #d3ddea;
    border-radius: 6px;
    padding: 6px;
}

QScrollArea {
    border: none;
}
QScrollBar:vertical {
    background: #eef4fb;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #bfd0e9;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #9fb8dc;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #eef4fb;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #bfd0e9;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #9fb8dc;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

QSplitter::handle {
    background: #d9e2f2;
}
QSplitter::handle:hover {
    background: #9fb8dc;
}
"""
