import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


class SidebarLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_long_paths_and_status_fit_sidebar_at_user_selected_width(self):
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(session_directory=directory)
            try:
                window.show()
                window.mode_combo.setCurrentText("Reflection")
                window.data_section.set_expanded(True)
                window.bg_section.set_expanded(True)
                long_name = "Measurement_" * 18 + ".csv"
                window.csv_edit.setText("D:/data/" + long_name)
                window.bg_status_label.setText("Background: 512 channels (" + long_name + ")")
                window.summary_label.setText("Axis X=" + "VeryLongAxisName" * 30)
                for width in (430, 360, 550):
                    window.main_splitter.setSizes([width, window.width() - width])
                    for _ in range(12):
                        self.app.processEvents()
                    viewport = window.sidebar_scroll.viewport()
                    self.assertLessEqual(window.sidebar_scroll.widget().width(), viewport.width())
                    for label in (window.active_output_label, window.bg_status_label, window.summary_label):
                        self.assertLessEqual(label.width(), viewport.width())
                self.assertIn(long_name[:-4], window.active_output_label.toolTip())
            finally:
                window.close()
