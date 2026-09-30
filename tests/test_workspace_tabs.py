import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import time
import threading
import hashlib
import json
import unittest

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.workers import BaseWorker


class WorkspaceTabsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.windows = []
        self.optical = self.root / 'optical.csv'
        frame = pd.DataFrame({'Vbg': [0, 1, 0, 1], 'Vtg': [0, 0, 1, 1]})
        for i, wave in enumerate(np.linspace(900, 1100, 16)):
            frame[str(wave)] = [10+i, 11+i, 12+i, 13+i]
        frame.to_csv(self.optical, index=False)
        self.transport = self.root / 'transport.csv'
        self.transport.write_text('Gate,Bias,Signal\nV,V,A\n0,1,1e-9\n0,2,2e-9\n1,2,3e-9\n')

    def wait(self, window):
        deadline = time.monotonic()+20
        while time.monotonic()<deadline:
            self.app.processEvents()
            if all(w._thread is None and not w._restoring_session for w in window.workspaces.values()):
                return
            time.sleep(.01)
        self.fail('Workspace workers did not finish')

    def tearDown(self):
        for window in self.windows:
            if hasattr(window, 'workspaces'):
                self.wait(window)
            window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def window(self):
        window = MainWindow(session_directory=self.root / 'sessions')
        self.windows.append(window)
        return window

    def test_tabs_own_independent_files_controls_and_plots(self):
        window = self.window()
        self.assertEqual(list(window.workspaces), ['PL', 'Reflection', 'Transport'])
        pl, ref, transport = window.workspaces.values()
        for workspace in (pl, ref):
            workspace._set_primary_csv_path(str(self.optical))
            workspace._start_csv_load()
        transport._set_primary_csv_path(str(self.transport))
        transport._start_csv_load()
        self.wait(window)
        self.assertEqual(pl.state.mode, 'PL')
        self.assertEqual(ref.state.mode, 'Reflection')
        self.assertIsNot(pl.state.data, ref.state.data)
        self.assertIsNot(pl.map_plot_tab, ref.map_plot_tab)
        self.assertTrue(pl.mode_combo.isHidden())
        pl._refresh_current_map_view()
        ref._set_background_paths([str(self.optical)])
        ref._start_background_load()
        self.wait(window)
        ref._refresh_current_map_view()
        self.wait(window)
        pl_figure = pl._current_map_figure()
        ref_figure = ref._current_map_figure()
        self.assertIsNotNone(pl_figure, pl.log_text.toPlainText())
        self.assertIsNotNone(ref_figure, ref.log_text.toPlainText())
        p = transport.transport_panel
        for combo, name in [(p.x_combo, 'Gate'), (p.y_combo, 'Bias'), (p.channel_combo, 'Signal')]:
            combo.setCurrentIndex(combo.findData(name))
        p.refresh_map()
        result = p.result
        fig = p.map_plot.current_figure
        for index in (2, 0, 1, 2):
            window.workspace_tabs.setCurrentIndex(index)
            self.app.processEvents()
        self.assertIs(p.result, result)
        self.assertIs(p.map_plot.current_figure, fig)
        self.assertIsNotNone(result)
        self.assertIs(pl._current_map_figure(), pl_figure)
        self.assertIs(ref._current_map_figure(), ref_figure)
        self.assertEqual(pl.state.csv_path, str(self.optical))

    def test_same_file_settings_are_separate_per_mode(self):
        window = self.window()
        for mode, ratio in [('PL', .7), ('Reflection', 1.3)]:
            workspace = window.workspaces[mode]
            workspace._set_primary_csv_path(str(self.optical))
            workspace._start_csv_load()
            self.wait(window)
            workspace.ratio_spin.setValue(ratio)
            workspace._save_session()
        self.assertNotEqual(window.workspaces['PL']._session_file(str(self.optical)),
                            window.workspaces['Reflection']._session_file(str(self.optical)))
        window.close()
        second = self.window()
        for mode, ratio in [('PL', .7), ('Reflection', 1.3)]:
            workspace = second.workspaces[mode]
            workspace._set_primary_csv_path(str(self.optical))
            workspace._start_csv_load()
            self.wait(second)
            self.assertEqual(workspace.state.mode, mode)
            self.assertAlmostEqual(workspace.ratio_spin.value(), ratio)

    def test_close_waits_for_worker_in_an_inactive_tab(self):
        window = self.window()
        window.show()
        gate = threading.Event()

        class ControlledWorker(BaseWorker):
            def process(self):
                gate.wait(5)
                return {}

        workspace = window.workspaces['Transport']
        workspace._run_worker(ControlledWorker(), lambda result: None, 'Test calculation')
        window.workspace_tabs.setCurrentIndex(0)
        try:
            window.close()
            self.assertTrue(window.isVisible())
            self.assertEqual(window.workspace_tabs.currentIndex(), 2)
        finally:
            gate.set()
        self.wait(window)
        window.close()
        self.assertFalse(window.isVisible())

    def test_legacy_recipe_migrates_only_to_its_original_mode(self):
        sessions = self.root / 'sessions'
        sessions.mkdir()
        key = os.path.normcase(os.path.abspath(self.optical))
        old = sessions / (hashlib.sha256(key.encode('utf-8')).hexdigest() + '.json')
        old.write_text(json.dumps({'version': 1, 'controls': {
            'mode_combo': 'Reflection', 'ratio_spin': .85},
            'views': [], 'line_specs': [], 'background_paths': []}))
        window = self.window()
        for mode in ('PL', 'Reflection'):
            workspace = window.workspaces[mode]
            workspace._set_primary_csv_path(str(self.optical))
            workspace._start_csv_load()
        self.wait(window)
        self.assertAlmostEqual(window.workspaces['PL'].ratio_spin.value(), 1.0)
        self.assertAlmostEqual(window.workspaces['Reflection'].ratio_spin.value(), .85)
        window.close()
        self.assertTrue(old.exists())
        self.assertTrue(window.workspaces['Reflection']._session_file(str(self.optical)).exists())
