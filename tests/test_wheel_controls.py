import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget
from ui.main_window import MainWindow


class WheelControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wheel(self, widget, delta):
        position = widget.rect().center()
        event = QWheelEvent(QPointF(position), QPointF(widget.mapToGlobal(position)),
                            QPoint(), QPoint(0, delta), Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        self.app.sendEvent(widget, event)
        self.app.processEvents()

    def test_focused_and_unfocused_controls_in_every_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(session_directory=directory)
            window.show()
            try:
                for index, workspace in enumerate(window.workspaces.values()):
                    window.workspace_tabs.setCurrentIndex(index)
                    combo = workspace.transport_panel.plot_kind_combo if index == 2 else workspace.map_type_combo
                    spin = workspace.sg_window_spin
                    for focused in (False, True):
                        for control in (combo, spin):
                            control.setFocus() if focused else control.clearFocus()
                            before = combo.currentIndex(), spin.value()
                            for delta in (-120, 120):
                                self.wheel(control, delta)
                                self.assertEqual((combo.currentIndex(), spin.value()), before)
            finally:
                window.close()

    def test_scroll_over_controls_scrolls_panel_but_keyboard_still_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            shell = MainWindow(session_directory=directory)
            scroll = QScrollArea()
            content = QWidget()
            layout = QVBoxLayout(content)
            spin, floating, combo = QSpinBox(), QDoubleSpinBox(), QComboBox()
            combo.setEditable(True)
            combo.addItems(['First', 'Second', 'Third'])
            combo.addItems([f'Item {index}' for index in range(30)])
            spin.setValue(10)
            floating.setValue(10.5)
            for widget in (spin, floating, combo):
                layout.addWidget(widget)
            layout.addSpacing(1400)
            scroll.setWidget(content)
            scroll.setWidgetResizable(True)
            scroll.resize(350, 240)
            scroll.show()
            self.app.processEvents()
            try:
                for control in (spin, spin.lineEdit(), floating, floating.lineEdit(), combo, combo.lineEdit()):
                    scroll.verticalScrollBar().setValue(0)
                    control.setFocus()
                    self.wheel(control, -120)
                    self.assertEqual((spin.value(), floating.value(), combo.currentIndex()), (10, 10.5, 0))
                    self.assertGreater(scroll.verticalScrollBar().value(), 0)
                QTest.keyClick(spin, Qt.Key_Up)
                self.assertEqual(spin.value(), 11)
                QTest.keyClick(combo, Qt.Key_Down)
                self.assertEqual(combo.currentIndex(), 1)
                scroll.ensureWidgetVisible(combo)
                combo.showPopup()
                self.app.processEvents()
                self.wheel(combo.view().viewport(), -120)
                self.assertEqual(combo.currentIndex(), 1)
                combo.hidePopup()
            finally:
                scroll.close()
                shell.close()
