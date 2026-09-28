import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from tests.test_session_memory import SessionMemoryFixture


class MapDisplayTests(SessionMemoryFixture, unittest.TestCase):
    def test_manual_limits_only_change_view_and_auto_restores_full_extent(self):
        window = self.save_reflection()
        figure = window._current_map_figure()
        original_limits = figure.axes[0].get_xlim()
        values = window.state.original_map["Z2D"].copy()
        with patch.object(window, "_start_analysis_refresh", side_effect=AssertionError("Display must not calculate")):
            window.x_range_auto_check.setChecked(False)
            window.x_range_min_spin.setValue(0)
            window.x_range_max_spin.setValue(.8)
            np.testing.assert_allclose(figure.axes[0].get_xlim(), [0, .8])
            window.map_cmap_combo.setCurrentText("plasma")
            self.assertEqual(figure.axes[0].collections[0].get_cmap().name, "plasma")
            window.x_range_min_spin.setValue(2)
            np.testing.assert_allclose(figure.axes[0].get_xlim(), [0, .8])
            window.x_range_auto_check.setChecked(True)
            np.testing.assert_allclose(figure.axes[0].get_xlim(), original_limits)
        np.testing.assert_allclose(window.state.original_map["Z2D"], values, equal_nan=True)

    def test_original_transformed_ranges_are_independent_and_persist(self):
        first = self.save_reflection()
        first.x_range_auto_check.setChecked(False)
        first.x_range_min_spin.setValue(0)
        first.x_range_max_spin.setValue(.8)
        first.map_axes_combo.setCurrentText("Transformed")
        first._refresh_current_map_view()
        self.wait_idle(first)
        self.assertTrue(first.x_range_auto_check.isChecked())
        first.y_range_auto_check.setChecked(False)
        first.y_range_min_spin.setValue(-.2)
        first.y_range_max_spin.setValue(.5)
        first.close()
        second = self.window()
        self.load(second, self.csv)
        np.testing.assert_allclose(second._current_map_figure().axes[0].get_ylim(), [-.2, .5])
        second.map_axes_combo.setCurrentText("Original")
        np.testing.assert_allclose(second._current_map_figure().axes[0].get_xlim(), [0, .8])
        self.assertTrue(second.y_range_auto_check.isChecked())

    def test_csv_export_remains_full_when_display_is_zoomed(self):
        window = self.save_reflection()
        window.x_range_auto_check.setChecked(False)
        window.x_range_min_spin.setValue(0)
        window.x_range_max_spin.setValue(.1)
        window._save_current_view("csv")
        exports = list(self.root.glob("sample_outputs/*.csv"))
        self.assertEqual(len(exports), 1)
        self.assertEqual(len(pd.read_csv(exports[0])), 4)

    def test_controls_wrap_without_horizontal_overflow(self):
        window = self.window()
        window.show()
        for width in (360, 620):
            window.main_splitter.setSizes([width, 1280 - width])
            for _ in range(12):
                self.app.processEvents()
            for widget in (window.x_range_max_spin, window.y_range_max_spin, window.refresh_all_maps_btn):
                from PySide6.QtCore import QPoint
                right = widget.mapTo(window.maps_workspace, QPoint(widget.width(), 0)).x()
                self.assertLessEqual(right, window.maps_workspace.width())

    def test_live_colormap_updates_preserve_missing_cell_color(self):
        data = pd.read_csv(self.csv)
        data.iloc[:3].to_csv(self.csv, index=False)
        window = self.save_reflection()
        mesh = window._current_map_figure().axes[0].collections[0]
        self.assertTrue(np.any(np.ma.getmaskarray(mesh.get_array())))
        window.map_cmap_combo.setCurrentText("plasma")
        np.testing.assert_allclose(mesh.get_cmap().get_bad(), [229 / 255, 231 / 255, 235 / 255, 1])
