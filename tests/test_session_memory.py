import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import time
import unittest

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


class SessionMemoryFixture:
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.windows = []
        self.csv = self.root / "sample.csv"
        self.bg = self.root / "background.csv"
        frame = pd.DataFrame({"Vbg": [0, 1, 0, 1], "Vtg": [0, 0, 1, 1]})
        for i, wavelength in enumerate(np.linspace(900, 1100, 16)):
            frame[str(wavelength)] = np.array([10, 11, 12, 13]) + i
        frame.to_csv(self.csv, index=False)
        frame.to_csv(self.bg, index=False)

    def tearDown(self):
        for window in self.windows:
            self.wait_idle(window)
            window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def window(self):
        window = MainWindow(session_directory=self.root / "sessions")
        self.windows.append(window)
        return window

    def wait_idle(self, window):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.app.processEvents()
            if window._thread is None and not window._restoring_session:
                return
            time.sleep(.01)
        self.fail("Worker/restore did not finish: " + window.log_text.toPlainText())

    def load(self, window, path):
        window._set_primary_csv_path(str(path))
        window._start_csv_load()
        self.wait_idle(window)
        self.assertIsNotNone(window.state.data, window.log_text.toPlainText())

    def save_reflection(self):
        window = self.window()
        self.load(window, self.csv)
        window.mode_combo.setCurrentText("Reflection")
        window.ratio_spin.setValue(.8)
        window.int_min_spin.setValue(1.15)
        window.int_max_spin.setValue(1.35)
        window.map_cmap_combo.setCurrentText("viridis")
        window._set_background_paths([str(self.bg)])
        window._start_background_load()
        self.wait_idle(window)
        window._refresh_current_map_view()
        self.wait_idle(window)
        self.assertIsNotNone(window.state.original_map, window.log_text.toPlainText())
        window._save_session()
        return window


class SessionMemoryTests(SessionMemoryFixture, unittest.TestCase):
    def test_restart_restores_background_parameters_and_recomputes_map(self):
        first = self.save_reflection()
        original = first.state.original_map
        first.close()
        second = self.window()
        self.load(second, self.csv)
        self.assertEqual(second.state.mode, "Reflection")
        self.assertEqual(second.state.background_paths, [str(self.bg)])
        self.assertAlmostEqual(second.ratio_spin.value(), .8)
        self.assertAlmostEqual(second.int_min_spin.value(), 1.15)
        self.assertEqual(second.map_cmap_combo.currentText(), "viridis")
        self.assertIsNotNone(second.state.original_map, second.log_text.toPlainText())
        self.assertIsNot(second.state.original_map, original)

    def test_switching_csv_keeps_independent_settings(self):
        window = self.save_reflection()
        other = self.root / "other.csv"
        other.write_bytes(self.csv.read_bytes())
        self.load(window, other)
        self.assertIsNone(window.state.background_spectra)
        self.assertEqual(window.state.current_ratio, window.ratio_spin.value())
        self.assertEqual(window.state.transform_convention, window._current_convention())
        window.ratio_spin.setValue(1.2)
        self.load(window, self.csv)
        self.assertAlmostEqual(window.ratio_spin.value(), .8)
        self.assertEqual(window.state.background_paths, [str(self.bg)])
        self.load(window, other)
        self.assertAlmostEqual(window.ratio_spin.value(), 1.2)

    def test_missing_background_preserves_settings_and_reports_path(self):
        first = self.save_reflection()
        first.close()
        self.bg.unlink()
        second = self.window()
        self.load(second, self.csv)
        self.assertIsNone(second.state.background_spectra)
        self.assertIsNone(second.state.original_map)
        self.assertAlmostEqual(second.ratio_spin.value(), .8)
        self.assertIn(str(self.bg), second.log_text.toPlainText())

    def test_reload_same_csv_uses_latest_settings(self):
        window = self.save_reflection()
        window.ratio_spin.setValue(.65)
        window._start_csv_load()
        self.wait_idle(window)
        self.assertAlmostEqual(window.ratio_spin.value(), .65)

    def test_parameter_changes_are_saved_without_closing(self):
        window = self.window()
        self.load(window, self.csv)
        window.ratio_spin.setValue(.72)
        deadline = time.monotonic() + 3
        while window._session_save_timer.isActive() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        second = self.window()
        self.load(second, self.csv)
        self.assertAlmostEqual(second.ratio_spin.value(), .72)

    def test_line_cuts_are_recomputed_after_restart(self):
        first = self.save_reflection()
        first._add_cut("doping", 0, .01)
        first._start_line_stage()
        self.wait_idle(first)
        self.assertTrue(first.state.line_cut_results)
        first.close()
        second = self.window()
        self.load(second, self.csv)
        self.assertTrue(second.state.line_cut_results, second.log_text.toPlainText())
        self.assertEqual(second._collect_line_specs()[0]["cut_type"], "doping")

    def test_corrupt_settings_do_not_block_loading(self):
        first = self.save_reflection()
        first.close()
        first._session_file(str(self.csv)).write_text('{"version": 1, "controls": {}, "line_specs": [null]}')
        second = self.window()
        self.load(second, self.csv)
        self.assertFalse(second._restoring_session)
        self.assertIn("using defaults", second.log_text.toPlainText())

    def test_incompatible_background_stops_restore_without_false_success(self):
        first = self.save_reflection()
        first.close()
        pd.DataFrame({"100": [1], "200": [2]}).to_csv(self.bg, index=False)
        second = self.window()
        self.load(second, self.csv)
        self.assertIsNone(second.state.original_map)
        self.assertNotIn("Saved analysis restored.", second.log_text.toPlainText())
