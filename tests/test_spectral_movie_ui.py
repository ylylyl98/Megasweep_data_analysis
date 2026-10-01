import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import unittest

from PySide6.QtWidgets import QApplication
import numpy as np

from tests.test_session_memory import SessionMemoryFixture
from ui.spectral_movie import SpectralMovieDialog
from spectral_movie import MovieOptions
from ui.workers import LineWorker


class MovieDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selection_preview_and_invalid_inputs(self):
        dialog = SpectralMovieDialog([-.3, 0, .01, 2], 'Doping', {}, dict(min=0, max=100))
        self.addCleanup(dialog.close)
        dialog.stride_spin.setValue(2)
        config = dialog.configuration()
        self.assertEqual(config['values'], [-.3, .01])
        self.assertIn('2 slices', dialog.summary_label.text())
        self.assertIn('0.50 s', dialog.summary_label.text())
        dialog.color_combo.setCurrentIndex(dialog.color_combo.findData('manual'))
        dialog.vmin_edit.setText('100')
        dialog.vmax_edit.setText('0')
        dialog.vmax_edit.editingFinished.emit()
        self.assertFalse(dialog.export_btn.isEnabled())
        self.assertTrue(dialog.error_label.text())
        dialog.vmin_edit.setText('0')
        dialog.vmax_edit.setText('200')
        dialog.vmax_edit.editingFinished.emit()
        self.assertTrue(dialog.export_btn.isEnabled())
        dialog.last_combo.setCurrentIndex(1)
        dialog.first_combo.setCurrentIndex(3)
        self.assertFalse(dialog.export_btn.isEnabled())

    def test_movie_ranges_are_independent_and_restore_before_png_defaults(self):
        png = dict(x=dict(auto=False, min=1.2, max=1.3), y=dict(auto=True, min=0., max=1.))
        dialog = SpectralMovieDialog([0, 1], 'Bias', png)
        self.addCleanup(dialog.close)
        controls = dialog.range_controls
        controls.controls['x'][1].setText('1.15')
        controls.controls['x'][2].setText('1.35')
        controls.controls['x'][2].editingFinished.emit()
        self.assertEqual(dialog.configuration()['ranges']['x'], dict(auto=False, min=1.15, max=1.35))
        self.assertEqual(png['x'], dict(auto=False, min=1.2, max=1.3))
        restored = SpectralMovieDialog([0, 1], 'Bias', png, recipe=dialog.configuration())
        self.addCleanup(restored.close)
        self.assertEqual(restored.configuration()['ranges']['x'], dict(auto=False, min=1.15, max=1.35))

    def test_recipe_roundtrip_keeps_playback_color_and_measured_subset(self):
        recipe = dict(first=0, last=2, stride=2,
                      options=dict(hold=.5, speed=2, fps=20, head=1, tail=2,
                                   direction='pingpong', repeats=2, color_mode='manual',
                                   width=640, height=480, crf=22), colors=dict(min=-100, max=200))
        dialog = SpectralMovieDialog([-.3, 0, .01, 2], 'Doping', {}, {}, recipe)
        self.addCleanup(dialog.close)
        config = dialog.configuration()
        self.assertEqual(config['values'], [0., 2.])
        self.assertEqual(config['options']['direction'], 'pingpong')
        self.assertEqual(config['options']['color_mode'], 'manual')
        self.assertEqual(config['colors'], dict(min=-100., max=200.))

    def test_advanced_controls_are_collapsed_and_keep_saved_values(self):
        dialog = SpectralMovieDialog([0, 1], 'Bias', recipe=dict(options=dict(speed=2, hold=.5)))
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        self.assertFalse(dialog.speed_spin.isVisible())
        self.assertTrue(dialog.range_controls.isVisible())
        self.assertEqual(dialog.configuration()['options']['speed'], 2)
        dialog.advanced_toggle.click()
        self.assertTrue(dialog.speed_spin.isVisible())
        dialog.speed_spin.setValue(3)
        dialog.advanced_toggle.click()
        self.assertFalse(dialog.speed_spin.isVisible())
        self.assertEqual(dialog.configuration()['options']['speed'], 3)

    def test_switch_to_auto_recovers_from_invalid_unused_manual_color_fields(self):
        dialog = SpectralMovieDialog([0, 1], 'Doping', {}, dict(min=0, max=100))
        self.addCleanup(dialog.close)
        dialog.color_combo.setCurrentIndex(dialog.color_combo.findData('manual'))
        dialog.vmin_edit.clear()
        self.assertFalse(dialog.export_btn.isEnabled())
        dialog.color_combo.setCurrentIndex(dialog.color_combo.findData('global'))
        self.assertTrue(dialog.export_btn.isEnabled())
        self.assertTrue(np.isfinite(list(dialog.configuration()['colors'].values())).all())


class MovieWorkspaceTests(SessionMemoryFixture, unittest.TestCase):
    def test_legacy_loaded_efield_cut_maps_to_actual_axis_before_movie_export(self):
        window = self.window()
        import pandas as pd
        frame = pd.read_csv(self.csv).rename(columns={'Vbg': 'Doping', 'Vtg': 'Efield'})
        frame.to_csv(self.csv, index=False)
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        for reversed_axes, expected_kind in ((False, 'y'), (True, 'x')):
            if reversed_axes:
                data = window.state.data.copy()
                data.update(x_data=data['y_data'], y_data=data['x_data'],
                            x_name='Efield', y_name='Doping')
                window.state.data = data
                panel.refresh()
            cut = LineWorker(window.state.data, [dict(cut_type='efield', c_value=0, epsilon=0)],
                             1., exact_coordinates=True).process()['line_cuts'][0]
            panel.show_existing_cut(cut)
            self.assertEqual(panel.fixed_combo.currentData(), expected_kind)
            self.assertEqual(panel.result['cut_type'], expected_kind)
            self.assertEqual(panel.result['fixed_axis_label'], 'Efield')
            panel.start_movie(dict(values=[0., 1.], first=0, last=1, stride=1,
                               options=vars(MovieOptions(width=420, height=288, hold=.1, fps=10)), colors={}))
            self.wait_idle(window)
        for path in self.root.rglob('*.settings.json'):
            info = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(info['metadata']['fixed_axis_label'], 'Efield')
            self.assertEqual(info['metadata']['axis_label'], 'Doping')

    def test_export_entry_requires_current_slice_and_recipe_is_restored(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        self.assertFalse(panel.movie_btn.isEnabled())
        panel.extract()
        self.wait_idle(window)
        self.assertTrue(panel.movie_btn.isEnabled())
        panel._movie_recipe = dict(first=0, last=1, stride=1, options=dict(hold=.5, fps=20))
        window._save_session()
        window.close()
        other = self.window()
        self.load(other, self.csv)
        self.assertEqual(other.spectral_slices_panel._movie_recipe['options']['fps'], 20)
        self.assertEqual(list(self.root.rglob('*.mp4')), [])

    def test_real_pl_movie_inherits_view_and_keeps_background_free(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        config = dict(values=[0., 1.], first=0., last=1., stride=1,
                      options=vars(MovieOptions(width=420, height=288, hold=.2, fps=10)),
                      colors=dict(min=0, max=100))
        panel.ranges.restore(dict(x=dict(auto=False, min=1.2, max=1.3),
                                  y=dict(auto=False, min=-.1, max=1.1)))
        panel.start_movie(config)
        self.assertIsNotNone(window._thread)
        self.assertTrue(panel._movie_progress.isEnabled())
        self.wait_idle(window)
        sidecar = next(self.root.rglob('*.settings.json'))
        info = json.loads(sidecar.read_text(encoding='utf-8'))
        self.assertEqual(info['view']['xlim'], [1.2, 1.3])
        self.assertEqual(info['view']['ylim'], [-.1, 1.1])
        self.assertEqual(info['metadata']['mode'], 'PL')
        self.assertEqual(info['metadata']['background_paths'], [])
        self.assertEqual(info['frame_count'], 4)
        self.assertTrue(panel.movie_btn.isEnabled())

    def test_reflection_derivative_movie_uses_current_processing_and_background(self):
        window = self.save_reflection()
        panel = window.spectral_slices_panel
        panel.coordinates_combo.setCurrentText('Original X/Y')
        panel.processing_combo.setCurrentIndex(panel.processing_combo.findData('second_derivative'))
        panel.derivative_window_spin.setValue(5)
        panel.extract()
        self.wait_idle(window)
        expected = panel.result['spectra'].copy()
        config = dict(values=[0., 1.], first=0., last=1., stride=1,
                      options=vars(MovieOptions(width=420, height=288, hold=.1, fps=10)), colors={})
        panel.start_movie(config)
        self.wait_idle(window)
        info = json.loads(next(self.root.rglob('*.settings.json')).read_text(encoding='utf-8'))
        self.assertEqual(info['metadata']['mode'], 'Reflection')
        self.assertEqual(info['metadata']['processing'], 'second_derivative')
        self.assertEqual(info['metadata']['derivative_window'], 5)
        self.assertEqual(info['metadata']['background_paths'], [str(self.bg)])
        self.assertAlmostEqual(info['view']['clim'][0], -info['view']['clim'][1])
        np.testing.assert_array_equal(panel.result['spectra'], expected)

    def test_cancel_remains_available_while_panel_is_disabled(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        panel.start_movie(dict(values=[0., 1.], first=0, last=1, stride=1,
                               options=vars(MovieOptions(width=420, height=288, hold=5)), colors={}))
        self.assertFalse(panel.isEnabled())
        self.assertTrue(panel._movie_progress.isEnabled())
        panel._movie_progress.canceled.emit()
        self.wait_idle(window)
        self.assertEqual(list(self.root.rglob('*.mp4')), [])
        self.assertIn('cancelled', window.log_text.toPlainText().lower())


if __name__ == '__main__':
    unittest.main()
