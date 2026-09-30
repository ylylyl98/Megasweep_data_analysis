import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import unittest
import numpy as np
import pandas as pd

from tests.test_session_memory import SessionMemoryFixture


class SpectralSlicesUITests(SessionMemoryFixture, unittest.TestCase):
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
        self.assertIsNone(panel.result)
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
        self.assertIsNone(panel.result)
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
        self.assertIsNone(panel.result)

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
        self.assertEqual(panel.fixed_combo.currentData(), 'doping')
        self.assertEqual(panel.fixed_combo.currentText(), 'Fixed Doping')

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
