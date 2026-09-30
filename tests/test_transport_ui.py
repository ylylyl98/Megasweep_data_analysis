import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import time
import unittest
import json

import pandas as pd
from PySide6.QtWidgets import QApplication

from ui.measurement_workspace import MeasurementWorkspace as MainWindow


class TransportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.csv = self.root / 'transport.csv'
        self.csv.write_text('Field,Bias,Current,PassIndex,FastDirection\nT,V,A,#,\n'
                            '0,1,1e-9,0,forward\n0,2,2e-9,0,forward\n'
                            '1,2,4e-9,1,reverse\n')
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            self.wait(window)
            window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def wait(self, window):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.app.processEvents()
            if window._thread is None and not window._restoring_session:
                return
            time.sleep(.01)
        self.fail(window.log_text.toPlainText())

    def load(self):
        window = MainWindow(session_directory=self.root / 'sessions')
        self.windows.append(window)
        window._set_primary_csv_path(str(self.csv))
        window.mode_combo.setCurrentText('Transport')
        window._start_csv_load()
        self.wait(window)
        return window

    def select_map(self, panel):
        for combo, name in [(panel.x_combo, 'Field'), (panel.y_combo, 'Bias'), (panel.channel_combo, 'Current')]:
            combo.setCurrentIndex(combo.findData(name))
        panel.refresh_map()
        self.assertIsNotNone(panel.result, panel.status.text())

    def test_header_choices_map_cut_exports_and_restart(self):
        window = self.load()
        self.assertEqual(window.state.mode, 'Transport')
        panel = window.transport_panel
        self.assertIsNotNone(panel.data, window.log_text.toPlainText())
        self.assertEqual(panel.x_combo.currentData(), 'Field')
        self.assertEqual(panel.y_combo.currentData(), 'Bias')
        self.assertEqual([panel.x_combo.itemData(i) for i in range(1, panel.x_combo.count())], ['Field', 'Bias', 'Current'])
        self.assertTrue(window.analysis_section.isHidden())
        self.select_map(panel)
        panel.fixed_combo.setCurrentText('Field')
        panel.cut_value_combo.setCurrentIndex(panel.cut_value_combo.findData(0.0))
        panel.refresh_cut()
        self.assertEqual(panel.cut['values'].tolist(), [1e-9, 2e-9])
        panel.export('map', 'csv')
        panel.export('cut', 'csv')
        panel.export('map', 'png')
        panel.export('cut', 'png')
        output = Path(window._dataset_output_dir())
        files = list(output.glob('*.csv'))
        self.assertEqual(len(files), 2)
        self.assertEqual(len(list(output.glob('*.png'))), 2, panel.status.text())
        for file in files:
            self.assertIn('Current', pd.read_csv(file).columns)
            expected = [1e-9, 2e-9] if file.name.startswith('cut_') else [1e-9, 2e-9, 4e-9]
            self.assertEqual(pd.read_csv(file)['Current'].tolist(), expected)
        panel.cmap_combo.setCurrentText('viridis')
        window._save_session()
        window.close()
        second = self.load()
        self.assertIsNotNone(second.transport_panel.result, second.log_text.toPlainText())
        self.assertIsNotNone(second.transport_panel.cut)
        self.assertEqual(second.transport_panel.cmap_combo.currentText(), 'viridis')

    def test_mode_switch_and_file_change_clear_stale_results(self):
        window = self.load()
        panel = window.transport_panel
        self.select_map(panel)
        other = self.root / 'other.csv'
        other.write_text('Temp,Voltage,Signal\n1,2,3\n')
        window._set_primary_csv_path(str(other))
        self.assertIsNone(panel.result)
        window.mode_combo.setCurrentText('PL')
        self.assertFalse(window.analysis_section.isHidden())
        window.mode_combo.setCurrentText('Transport')
        window._start_csv_load()
        self.wait(window)
        self.assertEqual(panel.data['columns'], ['Temp', 'Voltage', 'Signal'])

    def test_path_edit_disables_exports_before_editing_finishes(self):
        window = self.load()
        panel = window.transport_panel
        self.select_map(panel)
        window.csv_edit.setText(str(self.root / 'not-yet-selected.csv'))
        self.assertFalse(panel.isEnabled())
        self.assertFalse(panel.export_buttons[('map', 'csv')].isEnabled())
        window._save_session()
        self.assertIsNotNone(panel.result)
        window.csv_edit.setText(str(self.csv))
        self.assertTrue(panel.isEnabled())

    def test_transport_mode_round_trip_requires_reload(self):
        window = self.load()
        self.select_map(window.transport_panel)
        window.mode_combo.setCurrentText('PL')
        window.mode_combo.setCurrentText('Transport')
        self.assertIsNone(window.transport_panel.data)
        self.assertIsNone(window.transport_panel.result)
        self.assertFalse(window.transport_panel.export_buttons[('map', 'csv')].isEnabled())

    def test_completed_load_can_be_reloaded(self):
        window = self.load()
        self.assertTrue(window.load_csv_btn.isEnabled())
        self.assertTrue(window.transport_panel.isEnabled())

    def test_scientific_color_limits_and_second_cut_direction(self):
        window = self.load()
        panel = window.transport_panel
        self.select_map(panel)
        panel.min_edit.setText('-2e-9')
        panel.max_edit.setText('5e-9')
        panel.auto_scale.setChecked(False)
        self.assertEqual(panel.map_plot.current_figure.axes[0].collections[0].get_clim(), (-2e-9, 5e-9))
        panel.fixed_combo.setCurrentText('Bias')
        panel.cut_value_combo.setCurrentIndex(panel.cut_value_combo.findData(2.0))
        panel.refresh_cut()
        self.assertEqual(panel.cut['axis'], 'Field')
        self.assertEqual(panel.cut['values'].tolist(), [2e-9, 4e-9])

    def test_saved_manual_axes_take_priority_and_suggestion_can_be_reapplied(self):
        self.csv.with_name('transport_metadata.json').write_text(json.dumps({'params': {
            'axis_fast': 'Bias', 'axis_slow': 'Field', 'plot_x_axis': 'Bias'}}))
        window = self.load()
        panel = window.transport_panel
        self.assertEqual(panel.x_combo.currentData(), 'Bias')
        self.assertEqual(panel.y_combo.currentData(), 'Field')
        self.assertIn('metadata', panel.axis_hint.text().lower())
        self.select_map(panel)
        window._save_session()
        window.close()
        second = self.load()
        panel = second.transport_panel
        self.assertEqual(panel.x_combo.currentData(), 'Field')
        self.assertEqual(panel.y_combo.currentData(), 'Bias')
        self.assertIsNotNone(panel.result)
        panel.suggest_button.click()
        self.assertEqual(panel.x_combo.currentData(), 'Bias')
        self.assertEqual(panel.y_combo.currentData(), 'Field')
        self.assertIsNone(panel.result)

    def test_single_coordinate_curve_plot_export_and_restore(self):
        self.csv.write_text('Bias,Current,PassIndex,FastDirection\nV,A,#,\n'
                            '0,1e-9,0,forward\n1,2e-9,0,forward\n'
                            '1,3e-9,1,reverse\n0,4e-9,1,reverse\n')
        window = self.load()
        panel = window.transport_panel
        self.assertEqual(panel.x_combo.currentData(), 'Bias')
        self.assertEqual(panel.plot_kind_combo.currentData(), 'curve')
        self.assertFalse(panel.y_combo.isEnabled())
        panel.channel_combo.setCurrentIndex(panel.channel_combo.findData('Current'))
        panel.refresh_map()
        self.assertEqual(panel.result['kind'], 'curve')
        lines = panel.map_plot.current_figure.axes[0].lines
        self.assertEqual(len(lines), 2)
        self.assertEqual(list(lines[1].get_xdata()), [1, 0])
        self.assertFalse(panel.cut_button.isEnabled())
        panel.export('map', 'csv')
        panel.export('map', 'png')
        directory = Path(window._dataset_output_dir())
        self.assertEqual(len(list(directory.glob('curve_*.png'))), 1, panel.status.text())
        csv = next(directory.glob('curve_*.csv'))
        self.assertEqual(pd.read_csv(csv)['Current'].tolist(), [1e-9, 2e-9, 3e-9, 4e-9])
        window._save_session()
        window.close()
        second = self.load()
        self.assertEqual(second.transport_panel.plot_kind_combo.currentData(), 'curve')
        self.assertEqual(second.transport_panel.result['kind'], 'curve')

    def test_ambiguous_grid_is_not_automatically_selected(self):
        self.csv.write_text('Gate,Doping,Bias,Current\nV,V,V,A\n'
                            '0,0,0,1\n0,0,1,2\n1,2,1,3\n1,2,0,4\n')
        panel = self.load().transport_panel
        self.assertIsNone(panel.x_combo.currentData())
        self.assertFalse(panel.suggest_button.isEnabled())
        self.assertIn('Multiple', panel.axis_hint.text())

    def test_display_ranges_validate_redraw_export_and_restore(self):
        window = self.load()
        panel = window.transport_panel
        self.select_map(panel)
        original = panel.map_plot.current_figure.axes[0].get_xlim()
        auto, lower, upper = panel.map_ranges.controls['x']
        auto.setChecked(False)
        lower.setText('0.2'); upper.setText('0.8'); upper.editingFinished.emit()
        self.assertEqual(panel.map_plot.current_figure.axes[0].get_xlim(), (0.2, 0.8))
        lower.setText('nan'); lower.editingFinished.emit()
        self.assertEqual(panel.map_plot.current_figure.axes[0].get_xlim(), (0.2, 0.8))
        self.assertTrue(panel.map_ranges.error.text())
        lower.setText('0.2'); lower.editingFinished.emit()
        panel.cmap_combo.setCurrentText('viridis')
        self.assertEqual(panel.map_plot.current_figure.axes[0].get_xlim(), (0.2, 0.8))
        panel.export('map', 'csv')
        csv = next(Path(window._dataset_output_dir()).glob('map_*.csv'))
        self.assertEqual(len(pd.read_csv(csv)), 3)
        panel.export('map', 'png')
        self.assertEqual(panel.map_plot.current_figure.axes[0].get_xlim(), (0.2, 0.8))
        self.assertTrue(list(Path(window._dataset_output_dir()).glob('map_*.png')))
        window._save_session()
        second = self.load().transport_panel
        self.assertEqual(second.map_plot.current_figure.axes[0].get_xlim(), (0.2, 0.8))
        auto.setChecked(True)
        self.assertEqual(panel.map_plot.current_figure.axes[0].get_xlim(), original)

    def test_curve_signal_range_and_coordinate_change_reset(self):
        panel = self.load().transport_panel
        panel.plot_kind_combo.setCurrentIndex(panel.plot_kind_combo.findData('curve'))
        panel.x_combo.setCurrentIndex(panel.x_combo.findData('Bias'))
        panel.channel_combo.setCurrentIndex(panel.channel_combo.findData('Current'))
        panel.refresh_map()
        auto, lower, upper = panel.map_ranges.controls['y']
        auto.setChecked(False)
        lower.setText('1e-9'); upper.setText('3e-9'); upper.editingFinished.emit()
        self.assertEqual(panel.map_plot.current_figure.axes[0].get_ylim(), (1e-9, 3e-9))
        self.assertIn('Current', panel.map_ranges.labels['y'].toolTip())
        panel.x_combo.setCurrentIndex(panel.x_combo.findData('Field'))
        self.assertTrue(auto.isChecked())

    def test_cut_ranges_are_independent(self):
        panel = self.load().transport_panel
        self.select_map(panel)
        panel.fixed_combo.setCurrentText('Field')
        panel.cut_value_combo.setCurrentIndex(panel.cut_value_combo.findData(0.0))
        panel.refresh_cut()
        map_limits = panel.map_plot.current_figure.axes[0].get_ylim()
        auto, lower, upper = panel.cut_ranges.controls['y']
        auto.setChecked(False)
        lower.setText('1e-9'); upper.setText('2e-9'); upper.editingFinished.emit()
        self.assertEqual(panel.cut_plot.current_figure.axes[0].get_ylim(), (1e-9, 2e-9))
        self.assertEqual(panel.map_plot.current_figure.axes[0].get_ylim(), map_limits)

    def test_repeated_exports_version_png_and_only_changed_csv(self):
        window = self.load()
        panel = window.transport_panel
        self.select_map(panel)
        panel.export('map', 'csv')
        panel.export('map', 'png')
        directory = Path(window._dataset_output_dir())
        original_png = next(directory.glob('map_*.png'))
        original_bytes = original_png.read_bytes()
        auto, lower, upper = panel.map_ranges.controls['x']
        auto.setChecked(False)
        lower.setText('0.2'); upper.setText('0.8'); upper.editingFinished.emit()
        panel.export('map', 'png')
        panel.export('map', 'csv')
        self.assertEqual(len(list(directory.glob('map_*.png'))), 2)
        self.assertTrue(list(directory.glob('*_002.png')))
        self.assertEqual(original_png.read_bytes(), original_bytes)
        self.assertEqual(len(list(directory.glob('map_*.csv'))), 1)
        self.assertIn('Unchanged CSV; skipped:', window.log_text.toPlainText())
        panel.data['df'].loc[0, 'Current'] = 9e-9
        panel.refresh_map()
        panel.export('map', 'csv')
        self.assertEqual(len(list(directory.glob('map_*.csv'))), 2)
        self.assertEqual(pd.read_csv(next(directory.glob('*_002.csv')))['Current'].iloc[0], 9e-9)


if __name__ == '__main__':
    unittest.main()
