"""Exercise real plots and data through deferred UI updates."""
import time
import unittest

import numpy as np
from PySide6.QtWidgets import QCheckBox
from PySide6.QtTest import QTest

from tests.test_session_memory import SessionMemoryFixture


class AutoUpdateTests(SessionMemoryFixture, unittest.TestCase):
    def until(self, predicate, window):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate() and window._thread is None:
                return
            time.sleep(.01)
        self.fail(window.log_text.toPlainText())

    def transport(self):
        csv = self.root / 'transport.csv'
        csv.write_text('Field,Bias,Current,Other\n0,0,1,10\n0,1,2,20\n1,0,3,30\n1,1,4,40\n')
        window = self.window()
        window.mode_combo.setCurrentText('Transport')
        window._set_primary_csv_path(str(csv))
        window._start_csv_load()
        self.wait_idle(window)
        panel = window.transport_panel
        for combo, name in ((panel.x_combo, 'Field'), (panel.y_combo, 'Bias'), (panel.channel_combo, 'Current')):
            combo.setCurrentIndex(combo.findData(name))
        return window, panel

    def process_for(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.01)

    def test_transport_selection_automatically_builds_latest_map(self):
        window, panel = self.transport()
        panel.channel_combo.setCurrentIndex(panel.channel_combo.findData('Other'))
        self.until(lambda: panel.result is not None, window)
        self.assertEqual(panel.result['channel'], 'Other')
        self.assertEqual(panel.result['Z2D'].tolist(), [[10., 20.], [30., 40.]])

    def test_transport_manual_mode_preserves_plot_and_blocks_stale_export(self):
        window, panel = self.transport()
        panel.refresh_map()
        figure = panel.map_plot.current_figure
        controls = [c for c in panel.settings_widget.findChildren(QCheckBox) if c.text() == 'Auto Update']
        self.assertEqual(len(controls), 1, 'Transport needs an automatic/manual update choice')
        controls[0].setChecked(False)
        panel.channel_combo.setCurrentIndex(panel.channel_combo.findData('Other'))
        self.assertIs(panel.map_plot.current_figure, figure)
        self.assertFalse(panel.export_buttons[('map', 'csv')].isEnabled())
        panel.export('map', 'csv')
        self.assertEqual(set(self.root.rglob('*.csv')), {self.csv, self.bg, self.root / 'transport.csv'})
        self.process_for(.7)
        self.assertEqual(panel.result['channel'], 'Current')
        panel.refresh_button.click()
        self.assertEqual(panel.result['channel'], 'Other')

    def test_transport_cut_selection_updates_without_switching_tabs(self):
        window, panel = self.transport()
        panel.refresh_map()
        panel.tabs.setCurrentIndex(1)
        panel.fixed_combo.setCurrentText('Field')
        panel.cut_value_combo.setCurrentIndex(panel.cut_value_combo.findData(1.))
        self.until(lambda: panel.cut is not None, window)
        self.assertEqual(panel.cut['values'].tolist(), [3., 4.])
        panel.channel_combo.setCurrentIndex(panel.channel_combo.findData('Other'))
        self.until(lambda: panel.cut is not None and panel.cut['channel'] == 'Other', window)
        self.assertEqual(panel.cut['values'].tolist(), [30., 40.])
        self.assertEqual(panel.tabs.currentIndex(), 1)

    def test_optical_map_keeps_old_figure_then_updates_current_view_only(self):
        window = self.window()
        self.load(window, self.csv)
        window._refresh_current_map_view()
        self.wait_idle(window)
        figure = window.map_plot_tab.current_figure
        window.baseline_spin.setValue(3.)
        self.assertIs(window.map_plot_tab.current_figure, figure)
        self.assertFalse(window.save_current_png_btn.isEnabled())
        self.until(lambda: not window._dirty_views['intensity_original'], window)
        self.assertIsNot(window.map_plot_tab.current_figure, figure)
        self.assertIsNone(window.state.peak_map_original)
        self.assertIsNone(window.state.transformed_map)

    def test_slice_dropdown_and_processing_auto_update_retaining_plot(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.coordinates_combo.setCurrentText('Original X/Y')
        panel.extract()
        self.wait_idle(window)
        figure = panel.plot.current_figure
        panel.value_combo.setCurrentIndex(panel.value_combo.findData(1.))
        self.assertIs(panel.plot.current_figure, figure)
        self.assertFalse(panel.save_csv_btn.isEnabled())
        self.until(lambda: panel.result is not None and panel.result['c_value_used'] == 1., window)
        panel.processing_combo.setCurrentIndex(panel.processing_combo.findData('second_derivative'))
        self.until(lambda: panel.result is not None and panel.result.get('processing') == 'second_derivative', window)
        self.assertEqual(panel.result['c_value_used'], 1.)

    def test_outdated_map_worker_cannot_publish_old_settings(self):
        window = self.window()
        self.load(window, self.csv)
        window._refresh_current_map_view()
        window.baseline_spin.setValue(5.)
        self.until(lambda: not window._dirty_views['intensity_original'] and window._map_cache_signatures.get('intensity_original', (None,))[-1] == 5., window)
        actual = window.state.original_map['Z2D'].copy()
        window._refresh_current_map_view()
        self.wait_idle(window)
        np.testing.assert_allclose(window.state.original_map['Z2D'], actual)

    def test_load_builds_current_map_when_auto_baseline_is_off(self):
        window = self.window()
        window._set_primary_csv_path(str(self.csv))
        window.auto_baseline_check.setChecked(False)
        window._start_csv_load()
        self.wait_idle(window)
        self.until(lambda: window.state.original_map is not None, window)
        self.assertIsNone(window.state.peak_map_original)

    def test_inactive_workspace_waits_until_activated(self):
        window = self.window()
        window.set_auto_update_active(False)
        self.load(window, self.csv)
        self.process_for(.7)
        self.assertIsNone(window.state.original_map)
        window.set_auto_update_active(True)
        self.until(lambda: window.state.original_map is not None, window)

    def test_hidden_map_stays_stale_until_map_page_is_selected(self):
        window = self.window()
        self.load(window, self.csv)
        window._refresh_current_map_view()
        self.wait_idle(window)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        window.baseline_spin.setValue(7.)
        self.process_for(.7)
        self.assertTrue(window._dirty_views['intensity_original'])
        self.assertIsNone(window.state.original_map)
        window.workspace_tabs.setCurrentWidget(window.maps_workspace)
        self.until(lambda: not window._dirty_views['intensity_original'], window)

    def test_slice_invalid_typing_keeps_display_but_blocks_exports(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        figure = panel.plot.current_figure
        edit = panel.value_combo.lineEdit()
        edit.selectAll()
        QTest.keyClicks(edit, 'nan')
        edit.editingFinished.emit()
        self.process_for(.5)
        self.assertIs(panel.plot.current_figure, figure)
        self.assertFalse(panel.save_csv_btn.isEnabled())
        self.assertFalse(panel.plot.toolbar._actions['save_figure'].isEnabled())
        panel.save('csv')
        self.assertEqual(list(self.root.rglob('spectral_slices/**/*.csv')), [])

    def test_update_choices_survive_restart(self):
        window, panel = self.transport()
        panel.refresh_map()
        panel.map_updates.checkbox.setChecked(False)
        panel.cut_updates.checkbox.setChecked(False)
        window._save_session()
        window.close()
        second, restored = self.transport()
        self.assertFalse(restored.map_updates.checkbox.isChecked())
        self.assertFalse(restored.cut_updates.checkbox.isChecked())
        second.mode_combo.setCurrentText('PL')
        self.load(second, self.csv)
        second.map_updates.checkbox.setChecked(False)
        second.spectral_slices_panel.updates.checkbox.setChecked(False)
        second._save_session()
        second.close()
        third = self.window()
        self.load(third, self.csv)
        self.assertFalse(third.map_updates.checkbox.isChecked())
        self.assertFalse(third.spectral_slices_panel.updates.checkbox.isChecked())

    def test_closed_window_does_not_start_pending_calculation(self):
        window = self.window()
        self.load(window, self.csv)
        window.close()
        self.process_for(.7)
        self.assertIsNone(window._thread)

    def test_manual_slice_step_waits_for_update_now(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        panel.updates.checkbox.setChecked(False)
        panel.next_value_btn.click()
        self.process_for(.5)
        self.assertEqual(panel.result['c_value_used'], 0.)
        self.assertFalse(panel.save_csv_btn.isEnabled())
        panel.extract_btn.click()
        self.wait_idle(window)
        self.assertEqual(panel.result['c_value_used'], 1.)

    def test_rc_preview_retains_plot_on_scale_toggle_and_updates_automatically(self):
        window = self.save_reflection()
        window._preview_reflection_spectra()
        figure = window.line_plot_tab.current_figure
        window.background_scale_check.setChecked(False)
        self.assertIs(window.line_plot_tab.current_figure, figure)
        self.assertFalse(window.line_plot_tab.toolbar._actions['save_figure'].isEnabled())
        self.until(lambda: window.line_plot_tab.current_figure is not figure, window)
        self.assertTrue(window.line_plot_tab.toolbar._actions['save_figure'].isEnabled())

    def test_rc_manual_preview_waits_and_auto_updates_do_not_navigate(self):
        window = self.save_reflection()
        window._preview_reflection_spectra()
        figure = window.line_plot_tab.current_figure
        window.preview_updates.checkbox.setChecked(False)
        window.reflection_preview_vbg_spin.setValue(1.)
        self.process_for(.5)
        self.assertIs(window.line_plot_tab.current_figure, figure)
        window.workspace_tabs.setCurrentWidget(window.maps_workspace)
        window.preview_updates.checkbox.setChecked(True)
        self.process_for(.5)
        self.assertIs(window.line_plot_tab.current_figure, figure)
        self.assertIs(window.workspace_tabs.currentWidget(), window.maps_workspace)
        window.workspace_tabs.setCurrentWidget(window.line_workspace)
        self.until(lambda: window.line_plot_tab.current_figure is not figure, window)
        self.assertIn('1.000', window.line_plot_tab.current_figure.axes[0].get_title())

    def test_edited_source_path_disables_slice_and_preview_export_routes(self):
        window = self.save_reflection()
        window._preview_reflection_spectra()
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        window.csv_edit.setText(str(self.root / 'missing.csv'))
        self.assertFalse(panel.save_csv_btn.isEnabled())
        self.assertFalse(panel.movie_btn.isEnabled())
        self.assertFalse(panel.plot.toolbar._actions['save_figure'].isEnabled())
        self.assertFalse(window.line_plot_tab.toolbar._actions['save_figure'].isEnabled())
        window.csv_edit.setText(str(self.csv))
        self.assertTrue(panel.save_csv_btn.isEnabled())

    def test_explicit_legacy_slice_display_navigates_after_auto_update(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        panel.next_value_btn.click()
        self.wait_idle(window)
        cut = panel.result
        window.workspace_tabs.setCurrentWidget(window.maps_workspace)
        panel.show_existing_cut(cut)
        self.assertIs(window.workspace_tabs.currentWidget(), panel)

    def test_gate_transform_settings_preserve_original_rc_preview(self):
        window = self.save_reflection()
        window._preview_reflection_spectra()
        figure = window.line_plot_tab.current_figure
        window.ratio_spin.setValue(.81)
        window.convention_combo.setCurrentIndex(1)
        self.assertIs(window.line_plot_tab.current_figure, figure)


if __name__ == '__main__':
    unittest.main()
