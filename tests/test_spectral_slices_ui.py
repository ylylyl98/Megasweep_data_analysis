import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import unittest
import numpy as np
import pandas as pd
from unittest.mock import patch

from tests.test_session_memory import SessionMemoryFixture


class SpectralSlicesUITests(SessionMemoryFixture, unittest.TestCase):
    def test_auto_ranges_use_whole_sweep_and_x_zoom_survives_slice_changes(self):
        window = self.window()
        frame = pd.read_csv(self.csv)
        frame['Vtg'] = [0., 0., 1., 3.]
        frame.to_csv(self.csv, index=False)
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        full_x = (float(np.min(window.state.data['energy'])), float(np.max(window.state.data['energy'])))
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_ylim(), (0., 3.))
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_xlim(), full_x)
        self.set_range(panel, 'x', 1.2, 1.3)
        panel.next_value_btn.click()
        self.wait_idle(window)
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_ylim(), (0., 3.))
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_xlim(), (1.2, 1.3))
        panel.ranges.modes['x'].setCurrentIndex(panel.ranges.modes['x'].findData(True))
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_xlim(), full_x)
        panel.ranges.modes['x'].setCurrentIndex(panel.ranges.modes['x'].findData(False))
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_xlim(), (1.2, 1.3))
        from spectral_movie import MovieOptions
        worker = panel._movie_worker(dict(values=[0.], options=vars(MovieOptions()), colors={}), None)
        self.assertEqual(worker.ranges['y'], dict(auto=False, min=0., max=3.))
        panel.ranges.modes['x'].setCurrentIndex(panel.ranges.modes['x'].findData(True))
        saved = panel.ranges.recipe()
        panel.ranges.restore(saved)
        panel.ranges.attach(panel.plot.current_figure)
        with patch('ui.spectral_slices.LineWorker', side_effect=AssertionError('Range changes must not extract data')):
            panel.ranges.modes['x'].setCurrentIndex(panel.ranges.modes['x'].findData(False))
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_xlim(), (1.2, 1.3))

    def test_global_range_uses_transformed_coordinates_and_keeps_csv_complete(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        window.ratio_spin.setValue(.5)
        panel.coordinates_combo.setCurrentText('Transformed D/E')
        self.assertEqual(panel._global_limits('doping')['y'], (-.5, 1.))
        self.assertEqual(panel._global_limits('efield')['y'], (0., 1.5))
        panel.coordinates_combo.setCurrentText('Original X/Y')
        panel.extract()
        self.wait_idle(window)
        self.set_range(panel, 'x', 1.2, 1.3)
        panel.save('csv')
        exported = pd.read_csv(next(self.root.rglob('spectral_slices/**/*.csv')))
        self.assertEqual(exported.shape, (2, 18))
        self.assertTrue(any(float(name) < 1.2 for name in exported.columns[1:-1]))
        self.assertTrue(any(float(name) > 1.3 for name in exported.columns[1:-1]))

    def test_explicit_fixed_range_mode_preserves_limits_across_slices_and_restore(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        for axis, low, high in (('x', 1.2, 1.3), ('y', .1, .8)):
            mode = panel.ranges.modes[axis]
            self.assertTrue(mode.currentData())
            mode.setCurrentIndex(mode.findData(False))
            auto, lower, upper = panel.ranges.controls[axis]
            self.assertFalse(auto.isChecked())
            self.assertTrue(lower.isEnabled())
            lower.setText(str(low))
            upper.setText(str(high))
            upper.editingFinished.emit()
        panel.next_value_btn.click()
        self.wait_idle(window)
        axes = panel.plot.current_figure.axes[0]
        np.testing.assert_allclose(axes.get_xlim(), (1.2, 1.3))
        np.testing.assert_allclose(axes.get_ylim(), (.1, .8))
        window._save_session()
        window.close()
        other = self.window()
        self.load(other, self.csv)
        restored = other.spectral_slices_panel
        self.assertFalse(restored.ranges.modes['x'].currentData())
        self.assertFalse(restored.ranges.modes['y'].currentData())
        restored.extract()
        self.wait_idle(other)
        restored.ranges.modes['x'].setCurrentIndex(restored.ranges.modes['x'].findData(True))
        self.assertTrue(restored.ranges.controls['x'][0].isChecked())
        self.assertFalse(restored.ranges.controls['x'][1].isEnabled())
        self.assertLess(restored.plot.current_figure.axes[0].get_xlim()[0], 1.2)

    def test_larger_default_plot_fonts_are_shared_by_preview_and_batch(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        axes = panel.plot.current_figure.axes[0]
        self.assertEqual(axes.title.get_fontsize(), 16)
        self.assertEqual(axes.xaxis.label.get_fontsize(), 14)
        self.assertEqual(axes.get_xticklabels()[0].get_fontsize(), 12)
        from ui.exporting import save_figure
        sizes = []
        def record(figure, path):
            sizes.append(figure.axes[0].yaxis.label.get_fontsize())
            return save_figure(figure, path)
        with patch('ui.workers.save_figure', side_effect=record):
            panel.batch(['x'])
            self.wait_idle(window)
        self.assertEqual(sizes, [14., 14.])

    def test_batch_png_inherits_manual_ranges_and_colors_but_csv_stays_complete(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        self.set_range(panel, 'x', 1.2, 1.3)
        self.set_range(panel, 'y', .1, .8)
        panel.colors.auto.setChecked(False)
        panel.colors.lower.setText('0')
        panel.colors.upper.setText('100')
        panel.colors.upper.editingFinished.emit()
        from ui.exporting import save_figure
        figures = []
        def record(figure, path):
            axes = figure.axes[0]
            figures.append((axes.get_xlim(), axes.get_ylim(), axes.collections[0].get_clim()))
            return save_figure(figure, path)
        with patch('ui.workers.save_figure', side_effect=record):
            panel.batch(['x'])
            self.wait_idle(window)
        self.assertEqual(len(figures), 2, window.log_text.toPlainText())
        for xlim, ylim, clim in figures:
            np.testing.assert_allclose(xlim, (1.2, 1.3))
            np.testing.assert_allclose(ylim, (.1, .8))
            self.assertEqual(clim, (0., 100.))
        csv = next(self.root.rglob('spectral_slices/pl/x_fixed/*.csv'))
        self.assertEqual(pd.read_csv(csv).shape, (2, 18))

    def test_loaded_de_axes_use_one_coordinate_selection_with_measured_names(self):
        window = self.window()
        frame = pd.read_csv(self.csv).rename(columns={'Vbg': 'Doping', 'Vtg': 'Efield'})
        frame.to_csv(self.csv, index=False)
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        self.assertTrue(panel.coordinates_combo.isHidden())
        self.assertEqual(panel.fixed_combo.currentData(), 'x')
        self.assertEqual(panel.fixed_combo.currentText(), 'Fixed Doping')
        panel.extract()
        self.wait_idle(window)
        self.assertEqual(panel.result['fixed_axis_label'], 'Doping')
        self.assertEqual(panel.result['axis_label'], 'Efield')

    def test_fixed_value_buttons_follow_irregular_measured_coordinates(self):
        window = self.window()
        panel = window.spectral_slices_panel
        self.assertFalse(panel.previous_value_btn.isEnabled())
        self.assertFalse(panel.next_value_btn.isEnabled())
        frame = pd.read_csv(self.csv)
        frame = pd.concat([frame.iloc[:2], frame.iloc[:2], frame.iloc[:2]], ignore_index=True)
        frame['Vbg'] = [0, 0, .3, .3, 2, 2]
        frame['Vtg'] = [10, 20, 10, 20, 10, 20]
        frame.to_csv(self.csv, index=False)
        self.load(window, self.csv)
        self.assertFalse(panel.previous_value_btn.isEnabled())
        panel.next_value_btn.click()
        self.assertEqual(float(panel.value_combo.currentText()), .3)
        panel.next_value_btn.click()
        self.assertEqual(float(panel.value_combo.currentText()), 2)
        self.assertFalse(panel.next_value_btn.isEnabled())
        panel.previous_value_btn.click()
        self.assertEqual(float(panel.value_combo.currentText()), .3)
        panel.value_combo.setEditText('.5')
        panel.previous_value_btn.click()
        self.assertEqual(float(panel.value_combo.currentText()), .3)
        panel.value_combo.setEditText('invalid')
        self.assertFalse(panel.previous_value_btn.isEnabled())
        self.assertFalse(panel.next_value_btn.isEnabled())
        panel.fixed_combo.setCurrentIndex(panel.fixed_combo.findData('y'))
        self.assertEqual(float(panel.value_combo.currentText()), 10)
        panel.next_value_btn.click()
        self.assertEqual(float(panel.value_combo.currentText()), 20)

    def test_next_slice_refreshes_plot_and_keeps_processing_and_display_settings(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        panel.processing_combo.setCurrentIndex(panel.processing_combo.findData('second_derivative'))
        panel.derivative_window_spin.setValue(5)
        panel.extract()
        self.wait_idle(window)
        self.set_range(panel, 'x', 1.2, 1.3)
        panel.colors.auto.setChecked(False)
        panel.colors.lower.setText('-100')
        panel.colors.upper.setText('100')
        panel.colors.upper.editingFinished.emit()
        panel.next_value_btn.click()
        self.assertFalse(panel.next_value_btn.isEnabled())
        self.wait_idle(window)
        self.assertEqual(panel.result['c_value_used'], 1)
        self.assertEqual(panel.result['processing'], 'second_derivative')
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_xlim(), (1.2, 1.3))
        self.assertEqual(panel.plot.current_figure.axes[0].collections[0].get_clim(), (-100, 100))
        panel.previous_value_btn.click()
        self.wait_idle(window)
        self.assertEqual(panel.result['c_value_used'], 0)

    def set_range(self, panel, axis, low, high):
        auto, lower, upper = panel.ranges.controls[axis]
        auto.setChecked(False)
        lower.setText(str(low))
        upper.setText(str(high))
        upper.editingFinished.emit()

    def test_color_limits_change_live_and_derivative_resets_signal_scale(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        raw_result = panel.result
        artist = panel.plot.current_figure.axes[0].collections[0]
        auto_limits = artist.get_clim()
        panel.colors.auto.setChecked(False)
        panel.colors.lower.setText('1e2')
        panel.colors.upper.setText('2e2')
        panel.colors.upper.editingFinished.emit()
        self.assertEqual(artist.get_clim(), (100., 200.))
        self.assertIs(panel.result, raw_result)
        panel.colors.lower.setText('300')
        panel.colors.lower.editingFinished.emit()
        self.assertEqual(artist.get_clim(), (100., 200.))
        self.assertTrue(panel.colors.error.text())
        panel.colors.auto.setChecked(True)
        self.assertEqual(artist.get_clim(), auto_limits)
        panel.processing_combo.setCurrentIndex(panel.processing_combo.findData('second_derivative'))
        self.assertFalse(panel.save_csv_btn.isEnabled())
        self.assertIsNotNone(panel.plot.current_figure)
        self.assertTrue(panel.colors.auto.isChecked())
        panel.derivative_window_spin.setValue(5)
        panel.extract()
        self.wait_idle(window)
        self.assertEqual(panel.result['processing'], 'second_derivative')
        self.assertIn('d²PL/dE²', panel.axis_label.text())
        self.assertIn('d²PL/dE²', panel.plot.current_figure.axes[1].get_ylabel())
        panel.save('csv')
        csv = next(self.root.rglob('*d2dE2_w5.csv'))
        self.assertEqual(pd.read_csv(csv)['processing'].iloc[0], 'second_derivative')

    def test_processing_and_color_settings_restore(self):
        first = self.window()
        self.load_generic(first)
        panel = first.spectral_slices_panel
        panel.processing_combo.setCurrentIndex(panel.processing_combo.findData('second_derivative'))
        panel.derivative_window_spin.setValue(5)
        panel.colors.auto.setChecked(False)
        panel.colors.lower.setText('-2e3')
        panel.colors.upper.setText('2e3')
        panel.colors.upper.editingFinished.emit()
        first._save_session()
        first.close()
        second = self.window()
        self.load(second, self.csv)
        panel = second.spectral_slices_panel
        self.assertEqual(panel.processing_combo.currentData(), 'second_derivative')
        self.assertEqual(panel.derivative_window_spin.value(), 5)
        panel.extract()
        self.wait_idle(second)
        self.assertEqual(panel.plot.current_figure.axes[0].collections[0].get_clim(), (-2000., 2000.))

    def test_legacy_recipe_restore_does_not_overwrite_new_processing_settings(self):
        first = self.save_reflection()
        first.ratio_spin.setValue(1.)
        first._add_cut('efield', 0., .01)
        first._start_line_stage()
        self.wait_idle(first)
        self.assertTrue(first.state.line_cut_results)
        panel = first.spectral_slices_panel
        panel.processing_combo.setCurrentIndex(panel.processing_combo.findData('second_derivative'))
        panel.derivative_window_spin.setValue(5)
        self.set_range(panel, 'x', 1.2, 1.3)
        first._save_session()
        first.close()
        second = self.window()
        self.load(second, self.csv)
        panel = second.spectral_slices_panel
        self.assertEqual(panel.processing_combo.currentData(), 'second_derivative')
        self.assertEqual(panel.ranges.recipe()['x'], dict(auto=False, min=1.2, max=1.3))

    def test_optical_workspaces_have_one_slice_entry_and_explicit_axis_labels(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        for mode in ('PL', 'Reflection'):
            window.mode_combo.setCurrentText(mode)
            self.assertTrue(window.linecuts_section.isHidden())
            self.assertFalse(window.workspace_tabs.isTabVisible(1))
            self.assertTrue(window.workspace_tabs.isTabVisible(window.spectral_slices_tab_index))
            self.assertTrue(window.save_lines_png_btn.isHidden())
        self.assertIn('Doping_axis_a_set', panel.value_label.text())
        panel.fixed_combo.setCurrentIndex(panel.fixed_combo.findData('y'))
        self.assertIn('Vbias_axis_b_set', panel.value_label.text())
        self.assertIn('Energy (eV)', panel.ranges.labels['x'].text())
        self.assertIn('Doping_axis_a_set', panel.ranges.labels['y'].text())

    def test_display_ranges_apply_without_reextracting_or_truncating_csv(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        result = panel.result
        axes = panel.plot.current_figure.axes[0]
        full_x = axes.get_xlim()
        self.set_range(panel, 'x', 1.2, 1.3)
        self.set_range(panel, 'y', .1, .8)
        self.assertIs(panel.result, result)
        self.assertIsNone(window._thread)
        np.testing.assert_allclose(axes.get_xlim(), (1.2, 1.3))
        np.testing.assert_allclose(axes.get_ylim(), (.1, .8))
        self.set_range(panel, 'x', 'nan', 1.3)
        np.testing.assert_allclose(axes.get_xlim(), (1.2, 1.3))
        self.assertTrue(panel.ranges.error.text())
        panel.ranges.controls['x'][0].setChecked(True)
        np.testing.assert_allclose(axes.get_xlim(), full_x)
        panel.save('csv')
        csv = next(self.root.rglob('spectral_slices/pl/*.csv'))
        frame = pd.read_csv(csv)
        np.testing.assert_array_equal(frame.iloc[:, 0], [0, 1])
        self.assertEqual(frame.shape, (2, 18))

    def test_ranges_restore_and_reset_when_fixed_axis_changes(self):
        first = self.window()
        self.load_generic(first)
        panel = first.spectral_slices_panel
        panel.extract()
        self.wait_idle(first)
        self.set_range(panel, 'x', 1.2, 1.3)
        self.set_range(panel, 'y', .1, .8)
        first._save_session()
        first.close()
        second = self.window()
        self.load(second, self.csv)
        panel = second.spectral_slices_panel
        panel.extract()
        self.wait_idle(second)
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_xlim(), (1.2, 1.3))
        np.testing.assert_allclose(panel.plot.current_figure.axes[0].get_ylim(), (.1, .8))
        panel.fixed_combo.setCurrentIndex(panel.fixed_combo.findData('y'))
        self.assertTrue(panel.ranges.controls['x'][0].isChecked())
        self.assertTrue(panel.ranges.controls['y'][0].isChecked())

    def load_generic(self, window):
        frame = pd.read_csv(self.csv).rename(columns={'Vbg': 'Doping_axis_a_set', 'Vtg': 'Vbias_axis_b_set'})
        frame.to_csv(self.csv, index=False)
        self.load(window, self.csv)

    def test_pl_generic_slice_is_2d_in_separate_tab_and_preserves_linecuts(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        self.assertEqual(window.workspace_tabs.tabText(window.spectral_slices_tab_index), 'Spectral Slices')
        self.assertTrue(panel.extract_btn.isEnabled())
        self.assertTrue(panel.batch_both_btn.isEnabled())
        panel.extract_btn.click()
        self.wait_idle(window)
        self.assertIsNotNone(panel.result, window.log_text.toPlainText())
        np.testing.assert_array_equal(panel.result['axis_values'], [0, 1])
        self.assertEqual(panel.result['spectra'].shape, (2, 16))
        self.assertEqual(window.workspace_tabs.currentIndex(), window.spectral_slices_tab_index)
        self.assertEqual(panel.plot.current_figure.axes[0].get_xlabel(), 'Energy (eV)')
        self.assertIn('Vbias_axis_b_set', panel.plot.current_figure.axes[0].get_ylabel())
        self.assertIsNone(window.line_plot_tab.current_figure)
        panel.fixed_combo.setCurrentIndex(panel.fixed_combo.findData('y'))
        self.assertFalse(panel.save_csv_btn.isEnabled())
        self.assertIsNotNone(panel.plot.current_figure)
        panel.extract_btn.click()
        self.wait_idle(window)
        self.assertIn('Doping_axis_a_set', panel.plot.current_figure.axes[0].get_ylabel())

    def test_reflection_requires_background_and_invalidates_on_scale_change(self):
        window = self.window()
        self.load_generic(window)
        window.mode_combo.setCurrentText('Reflection')
        panel = window.spectral_slices_panel
        self.assertFalse(panel.extract_btn.isEnabled())
        window._set_background_paths([str(self.bg)])
        window._start_background_load()
        self.wait_idle(window)
        window.background_scale_check.setChecked(False)
        self.assertTrue(panel.extract_btn.isEnabled())
        panel.extract_btn.click()
        self.wait_idle(window)
        self.assertIsNotNone(panel.result, window.log_text.toPlainText())
        np.testing.assert_allclose(panel.result['spectra'][0],
                                   (np.arange(16) + 10) / (np.arange(16) + 11.5) - 1)
        window.background_scale_check.setChecked(True)
        window.scale_left_min_spin.setValue(window.scale_left_min_spin.value() + .01)
        self.assertFalse(panel.save_csv_btn.isEnabled())
        self.assertIsNotNone(panel.plot.current_figure)

    def test_follow_map_transformed_and_explicit_original_are_independent(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        self.assertEqual(panel.fixed_combo.currentData(), 'x')
        window.map_axes_combo.setCurrentText('Transformed')
        self.assertEqual(panel.fixed_combo.currentData(), 'doping')
        self.assertTrue(panel.batch_both_btn.isEnabled())
        panel.coordinates_combo.setCurrentText('Original X/Y')
        self.assertEqual(panel.fixed_combo.currentData(), 'x')
        panel.value_combo.setEditText('.8')
        panel.extract_btn.click()
        self.wait_idle(window)
        self.assertEqual(panel.result['c_value_used'], 1)

    def test_slice_settings_restore_per_file(self):
        first = self.window()
        self.load_generic(first)
        panel = first.spectral_slices_panel
        panel.coordinates_combo.setCurrentText('Original X/Y')
        panel.fixed_combo.setCurrentIndex(panel.fixed_combo.findData('y'))
        panel.value_combo.setEditText('1')
        panel.epsilon_spin.setValue(.01)
        first._save_session()
        first.close()
        second = self.window()
        self.load(second, self.csv)
        restored = second.spectral_slices_panel
        self.assertEqual(restored.coordinates_combo.currentText(), 'Original X/Y')
        self.assertEqual(restored.fixed_combo.currentData(), 'y')
        self.assertEqual(float(restored.value_combo.currentText()), 1)
        self.assertEqual(restored.epsilon_spin.value(), .01)

    def test_new_tab_uses_measured_de_values_and_orders_loaded_labels(self):
        window = self.window()
        frame = pd.read_csv(self.csv).rename(columns={'Vbg': 'Doping', 'Vtg': 'Efield'})
        frame['Doping'] = [0., .0005, 0., .0005]
        frame.to_csv(self.csv, index=False)
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.coordinates_combo.setCurrentText('Transformed D/E')
        self.assertEqual([panel.value_combo.itemData(i) for i in range(panel.value_combo.count())], [0., .0005])
        panel.extract_btn.click()
        self.wait_idle(window)
        self.assertEqual(panel.result['c_value_used'], 0.)
        np.testing.assert_array_equal(panel.result['spectra'][:, 0], [10, 12])
        # The shared extraction API also accepts explicitly reversed loaded D/E.
        data = window.state.data.copy()
        data.update(x_data=data['y_data'], y_data=data['x_data'], x_name='Efield', y_name='Doping')
        window.state.data = data
        panel.refresh()
        self.assertEqual(panel.fixed_combo.currentData(), 'x')
        self.assertEqual(panel.fixed_combo.currentText(), 'Fixed Efield')

    def test_single_point_cannot_be_misrepresented_as_a_2d_slice(self):
        window = self.window()
        self.load_generic(window)
        # Remove all but one varying coordinate at each fixed X.
        frame = pd.read_csv(self.csv).iloc[:2]
        single = self.root / 'single.csv'
        frame.to_csv(single, index=False)
        self.load(window, single)
        panel = window.spectral_slices_panel
        panel.extract_btn.click()
        self.wait_idle(window)
        self.assertIsNone(panel.result)
        self.assertIn('at least two', panel.status_label.text())

    def test_batch_button_exports_raw_pl_slices_and_counts_match_preview(self):
        window = self.window()
        self.load_generic(window)
        panel = window.spectral_slices_panel
        panel.preview_btn.click()
        self.assertEqual(panel.status_label.text().count('2 slices'), 2)
        panel.batch_both_btn.click()
        self.wait_idle(window)
        self.assertIn('4 slices', panel.status_label.text())
        files = list(self.root.rglob('spectral_slices/pl/**/*.csv'))
        self.assertEqual(len(files), 4, window.log_text.toPlainText())


if __name__ == '__main__':
    unittest.main()
