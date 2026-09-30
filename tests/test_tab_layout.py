import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.widgets import PlotTab


class TabLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_logs_can_be_reopened_and_errors_are_visible_in_each_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(session_directory=directory)
            try:
                window.show()
                for index, workspace in enumerate(window.workspaces.values()):
                    window.workspace_tabs.setCurrentIndex(index)
                    self.app.processEvents()
                    self.assertTrue(workspace.log_text.isHidden())
                    workspace.log_toggle.click()
                    self.assertFalse(workspace.log_text.isHidden())
                    workspace.log_toggle.click()
                    workspace._append_log('Test error', 'error')
                    self.assertFalse(workspace.log_text.isHidden())
                    self.assertIn('Test error', workspace.log_text.toPlainText())
            finally:
                window.close()

    def test_curve_hides_map_controls_and_restores_them(self):
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(session_directory=directory)
            try:
                workspace = window.workspaces['Transport']
                panel = workspace.transport_panel
                panel.plot_kind_combo.setCurrentIndex(panel.plot_kind_combo.findData('curve'))
                self.assertTrue(panel.y_row.isHidden())
                self.assertTrue(panel.color_controls.isHidden())
                self.assertTrue(workspace.transport_cuts_section.isHidden())
                panel.plot_kind_combo.setCurrentIndex(panel.plot_kind_combo.findData('map'))
                self.assertFalse(panel.y_row.isHidden())
                self.assertFalse(panel.color_controls.isHidden())
                self.assertFalse(workspace.transport_cuts_section.isHidden())
            finally:
                window.close()

    def test_plot_labels_fit_after_canvas_resize(self):
        tab = PlotTab('Map')
        figure = Figure(figsize=(9, 7))
        axes = figure.add_subplot()
        axes.plot([0, 1], [0, 1])
        axes.set(title='Measurement map', xlabel='Gate voltage (V)', ylabel='Current (A)')
        figure.tight_layout()
        tab.set_figure(figure)
        tab.show()
        try:
            for width, height in ((820, 520), (650, 320), (1000, 650)):
                tab.resize(width, height)
                for _ in range(5):
                    self.app.processEvents()
                tab.canvas.draw()
                renderer = tab.canvas.get_renderer()
                for label in (axes.title, axes.xaxis.label, axes.yaxis.label):
                    bbox = label.get_window_extent(renderer)
                    self.assertGreaterEqual(bbox.x0, 0)
                    self.assertGreaterEqual(bbox.y0, 0)
                    self.assertLessEqual(bbox.x1, figure.bbox.width)
                    self.assertLessEqual(bbox.y1, figure.bbox.height)
        finally:
            tab.close()

    def test_toolbar_save_preserves_existing_png(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'toolbar.png'
            tab = PlotTab('Map')
            figure = Figure()
            figure.add_subplot().plot([0, 1], [0, 1])
            tab.set_figure(figure)
            messages = []
            tab.export_message.connect(lambda message, level: messages.append(message))
            try:
                with patch('ui.widgets.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                    tab.toolbar.save_figure()
                    original = path.read_bytes()
                    figure.axes[0].set_xlim(0, .5)
                    tab.toolbar.save_figure()
                self.assertEqual(path.read_bytes(), original)
                self.assertTrue(path.with_name('toolbar_002.png').is_file())
                self.assertIn('toolbar_002.png', messages[-1])
            finally:
                tab.close()
