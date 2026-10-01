"""Semantic Fluent-inspired Qt styles. Metrics are adapted for scientific forms."""
import json
from pathlib import Path

from PySide6.QtGui import QColor, QPalette

BODY_FONT_PX = 14
CAPTION_FONT_PX = 12
_TOKENS = json.loads(Path(__file__).with_name('fluent_tokens.json').read_text(encoding='utf-8'))


def theme_colors(theme='light'):
    return {name: spec[theme] for name, spec in _TOKENS['aliases'].items()}


def theme_palette(theme='light'):
    colors = theme_colors(theme)
    palette = QPalette()
    roles = {
        QPalette.Window: 'window_background', QPalette.WindowText: 'text_primary',
        QPalette.Base: 'surface_background', QPalette.AlternateBase: 'surface_tertiary',
        QPalette.ToolTipBase: 'surface_background', QPalette.ToolTipText: 'text_primary',
        QPalette.Text: 'text_primary', QPalette.Button: 'surface_background',
        QPalette.ButtonText: 'text_primary', QPalette.Highlight: 'selection_strong_background',
        QPalette.HighlightedText: 'selection_strong_foreground',
        QPalette.PlaceholderText: 'text_tertiary', QPalette.Link: 'brand_foreground',
    }
    for role, name in roles.items():
        palette.setColor(role, QColor(colors[name]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(colors['text_disabled']))
    return palette


_TEMPLATE = '''
QWidget { font-size: @body@px; color: @text_primary@; background: @window_background@; }
QLabel { background: transparent; }
QLabel[fluentRole="caption"] { color: @text_tertiary@; font-size: @caption@px; }
QLabel[fluentSeverity="danger"] { color: @danger_foreground@; }
QLabel[fluentRole="title"] { font-size: 20px; font-weight: 600; }
QLabel[fluentRole="subtitle"] { font-size: 16px; font-weight: 600; }
QWidget[class="sectionContent"], QWidget[class="inlineRow"], QWidget[fluentRole="content"] { background: transparent; }
QFrame#StageCard, QFrame#PanelCard { background: @surface_background@; border: 1px solid @border_subtle@; border-radius: 8px; }
QGroupBox { background: @surface_background@; border: 1px solid @border_subtle@;
    border-radius: 8px; margin-top: 20px; padding: 12px 8px 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: @text_secondary@; }
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: @surface_background@; color: @text_primary@; border: 1px solid @border_primary@;
    border-radius: 6px; padding: 4px 8px; min-height: 20px;
    selection-background-color: @selection_strong_background@; selection-color: @selection_strong_foreground@; }
QLineEdit:hover, QDoubleSpinBox:hover, QSpinBox:hover, QComboBox:hover { border-color: @border_accessible@; }
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus { border-color: @focus_border@; }
QLineEdit:read-only { background: @surface_secondary@; color: @text_secondary@; }
QLineEdit:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {
    background: @surface_disabled@; color: @text_tertiary@; border-color: @border_subtle@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url("@arrow_down@"); width: 14px; height: 14px; }
QComboBox::down-arrow:disabled { image: url("@arrow_down_disabled@"); }
QSpinBox, QDoubleSpinBox { padding-right: 22px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: padding; subcontrol-position: top right;
    width: 20px; height: 14px; border: none; border-top-right-radius: 5px; background: transparent; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: padding; subcontrol-position: bottom right;
    width: 20px; height: 14px; border: none; border-bottom-right-radius: 5px; background: transparent; }
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: @surface_background_hover@; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background: @surface_background_pressed@; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("@arrow_up@"); width: 12px; height: 12px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("@arrow_down@"); width: 12px; height: 12px; }
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:off { image: url("@arrow_up_disabled@"); }
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled,
QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:off { image: url("@arrow_down_disabled@"); }
QSpinBox[readOnly="true"]::up-button, QSpinBox[readOnly="true"]::down-button,
QDoubleSpinBox[readOnly="true"]::up-button, QDoubleSpinBox[readOnly="true"]::down-button { background: transparent; }
QComboBox QAbstractItemView { background: @surface_background@; color: @text_primary@; border: 1px solid @border_primary@;
    selection-background-color: @selection_subtle_background@; selection-color: @selection_subtle_foreground@; padding: 4px; }
QPushButton, QToolButton { background: @surface_background@; color: @text_primary@; border: 1px solid @border_primary@;
    border-radius: 6px; padding: 5px 10px; min-height: 20px; font-weight: 500; }
QToolButton { padding: 4px 7px; }
QPushButton:hover, QToolButton:hover { background: @surface_background_hover@; border-color: @border_accessible@; }
QPushButton:pressed, QToolButton:pressed { background: @surface_background_pressed@; }
QPushButton:checked, QToolButton:checked { background: @selection_subtle_background@; color: @brand_foreground@; }
QPushButton:focus, QToolButton:focus { border-color: @focus_border@; }
QPushButton:disabled, QToolButton:disabled { background: @surface_disabled@; color: @text_tertiary@; border-color: @border_subtle@; }
QPushButton[class="primary"], QPushButton[fluentAppearance="primary"] {
    background: @brand_background@; color: @selection_strong_foreground@; border-color: @brand_background@; font-weight: 600; }
QPushButton[class="primary"]:hover, QPushButton[fluentAppearance="primary"]:hover { background: @brand_background_hover@; }
QPushButton[class="primary"]:pressed, QPushButton[fluentAppearance="primary"]:pressed { background: @brand_background_pressed@; }
QPushButton[class="primary"]:focus, QPushButton[fluentAppearance="primary"]:focus { border-color: @focus_border@; }
QPushButton[class="primary"]:disabled, QPushButton[fluentAppearance="primary"]:disabled {
    background: @surface_disabled@; color: @text_tertiary@; border-color: @border_subtle@; }
QPushButton[class="ghost"] { background: transparent; border-color: @border_subtle@; }
QToolButton[class="sectionToggle"] { background: transparent; border: 1px solid transparent; border-radius: 6px;
    color: @text_secondary@; font-weight: 600; padding: 5px 8px; text-align: left; }
QToolButton[class="sectionToggle"]:hover { background: @surface_background_hover@; }
QToolButton[class="sectionToggle"]:checked { color: @brand_foreground@; }
QToolButton[class="sectionToggle"]:focus { border-color: @focus_border@; }
QCheckBox, QRadioButton { background: transparent; spacing: 6px; padding: 2px; border: 1px solid transparent; }
QCheckBox:disabled, QRadioButton:disabled { color: @text_tertiary@; }
QCheckBox:focus, QRadioButton:focus { border-color: @focus_border@; }
QTableWidget, QTableView, QListView, QTreeView { background: @surface_background@; color: @text_primary@;
    alternate-background-color: @surface_secondary@; gridline-color: @border_subtle@;
    border: 1px solid @border_subtle@; border-radius: 6px;
    selection-background-color: @selection_subtle_background@; selection-color: @selection_subtle_foreground@; }
QHeaderView::section { background: @surface_secondary@; color: @text_secondary@;
    border: none; border-bottom: 1px solid @border_subtle@; padding: 7px 8px; font-weight: 600; }
QTabWidget::pane { border: 1px solid @border_subtle@; border-radius: 6px; background: @surface_background@; }
QTabBar::tab { background: transparent; color: @text_tertiary@; border: none;
    border-bottom: 2px solid transparent; padding: 8px 14px; margin-right: 2px; }
QTabBar::tab:selected { background: @surface_background@; color: @text_primary@;
    border-bottom-color: @brand_background@; font-weight: 600; }
QTabBar::tab:hover:!selected { background: @surface_background_hover@; color: @text_secondary@; }
QTextEdit, QPlainTextEdit { background: @surface_background@; color: @text_primary@;
    border: 1px solid @border_subtle@; border-radius: 6px; padding: 6px; }
QScrollArea { border: none; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:vertical { background: @border_primary@; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:horizontal { background: @border_primary@; border-radius: 5px; min-width: 28px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: @border_accessible@; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: @border_subtle@; }
QSplitter::handle:hover { background: @brand_border@; }
QSlider::groove:horizontal { height: 4px; background: @border_subtle@; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @brand_background@; border-radius: 2px; }
QSlider::handle:horizontal { background: @surface_background@; border: 2px solid @brand_border@;
    width: 12px; margin: -6px 0; border-radius: 7px; }
QSlider::handle:horizontal:focus { border-color: @focus_border@; }
QSlider::handle:horizontal:disabled { border-color: @text_tertiary@; }
QProgressBar { background: @surface_tertiary@; border: 1px solid @border_subtle@; border-radius: 6px;
    min-height: 18px; text-align: center; color: @text_primary@; }
QProgressBar::chunk { background: @brand_background_subtle@; border-radius: 5px; }
QToolBar { border: none; background: @surface_secondary@; spacing: 4px; padding: 2px; }
QLabel[class="videoPreview"] { background: @surface_tertiary@; color: @text_tertiary@; border-radius: 8px; }
QLabel[fluentRole="placeholder"] { color: @text_tertiary@; border: 1px dashed @border_primary@;
    padding: 36px; background: @surface_secondary@; border-radius: 8px; }
'''


def theme_style(theme='light'):
    style = _TEMPLATE.replace('@body@', str(BODY_FONT_PX)).replace('@caption@', str(CAPTION_FONT_PX))
    for name, value in theme_colors(theme).items():
        style = style.replace(f'@{name}@', value)
    for direction in ('up', 'down'):
        for state in ('normal', 'disabled'):
            name = f'arrow_{direction}' + ('_disabled' if state == 'disabled' else '')
            path = Path(__file__).with_name('icons') / f'chevron-{direction}-{theme}-{state}.svg'
            style = style.replace(f'@{name}@', path.as_posix())
    return style


# Preserve existing imports while sharing semantic styles across both themes.
_LIGHT_STYLE = theme_style('light')
_STYLE = theme_style('dark')
