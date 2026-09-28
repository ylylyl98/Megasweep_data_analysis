from unittest.mock import patch
import unittest

import numpy as np
import pandas as pd

from tests.test_session_memory import SessionMemoryFixture
from ui import workers
from PySide6.QtCore import QThread


class RefreshCacheTests(SessionMemoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        sample = pd.read_csv(self.csv)
        background = sample.copy()
        for i, column in enumerate(sample.columns[2:]):
            sample[column] = 10 + 100 * np.exp(-((i - 8) / 2.5) ** 2)
            background[column] = 10
        sample.to_csv(self.csv, index=False)
        background.to_csv(self.bg, index=False)

    def test_refresh_result_rendering_runs_on_gui_thread(self):
        window = self.window()
        self.load(window, self.csv)
        render_threads = []
        original = window._on_analysis_refresh_ready

        def observe(payload):
            render_threads.append(QThread.currentThread() == window.thread())
            original(payload)

        window._on_analysis_refresh_ready = observe
        window._refresh_current_map_view()
        self.wait_idle(window)
        self.assertEqual(render_threads, [True])

    def test_refresh_and_color_changes_reuse_peak_values(self):
        window = self.save_reflection()
        window.map_type_combo.setCurrentText("RC Peak Position")
        with patch.object(workers, "compute_rc_peak_position_map", wraps=workers.compute_rc_peak_position_map) as compute:
            window._refresh_current_map_view()
            self.wait_idle(window)
            expected = window.state.peak_map_original["Z2D"].copy()
            window.map_cmap_combo.setCurrentText("plasma")
            window._refresh_current_map_view()
            self.wait_idle(window)
            self.assertEqual(compute.call_count, 1)
            np.testing.assert_allclose(window.state.peak_map_original["Z2D"], expected, equal_nan=True)
            self.assertEqual(window._current_map_figure().axes[0].collections[0].get_cmap().name, "plasma")
            window.int_min_spin.setValue(1.16)
            window._refresh_current_map_view()
            self.wait_idle(window)
            self.assertEqual(compute.call_count, 2)

    def test_ratio_and_coordinate_changes_reuse_spectral_peak_result(self):
        window = self.save_reflection()
        window.map_type_combo.setCurrentText("RC Peak Position")
        with patch.object(workers, "compute_rc_peak_position_map", wraps=workers.compute_rc_peak_position_map) as compute:
            window._refresh_current_map_view()
            self.wait_idle(window)
            window.map_axes_combo.setCurrentText("Transformed")
            window._refresh_current_map_view()
            self.wait_idle(window)
            window.ratio_spin.setValue(.7)
            window._refresh_current_map_view()
            self.wait_idle(window)
            self.assertEqual(compute.call_count, 1)
            self.assertIsNotNone(window.state.peak_map_transformed)
            self.assertEqual(window.state.peak_map_transformed["ratio"], .7)
            window.sg_window_spin.setValue(7)
            window._refresh_current_map_view()
            self.wait_idle(window)
            self.assertEqual(compute.call_count, 2)

    def test_refresh_all_skips_valid_peaks_but_background_reload_invalidates_them(self):
        window = self.save_reflection()
        with patch.object(workers, "compute_rc_peak_position_map", wraps=workers.compute_rc_peak_position_map) as compute:
            window._refresh_all_maps()
            self.wait_idle(window)
            window._refresh_all_maps()
            self.wait_idle(window)
            self.assertEqual(compute.call_count, 1)
            window._start_background_load()
            self.wait_idle(window)
            window._refresh_all_maps()
            self.wait_idle(window)
            self.assertEqual(compute.call_count, 2)
