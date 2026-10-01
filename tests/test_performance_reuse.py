"""Regression checks for avoidable computation, with real outputs retained."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
import imageio_ffmpeg
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent

import spectral_movie as movie
import megasweep_analysis as analysis
from tests.test_spectral_movie import cut
from tests.test_spectral_slices import sample_data
from tests.test_session_memory import SessionMemoryFixture
from tests import test_transport_ui as transport_fixture
from ui import workers


class WorkerReuseTests(unittest.TestCase):
    def test_single_point_coordinate_discovery_does_not_scan_each_candidate(self):
        with patch.object(analysis.np, 'unique', wraps=analysis.np.unique) as unique:
            values = analysis.find_all_cut_values([0., 0., 1., 3., 4., np.nan],
                        [0., 1., 2., 4., np.nan, 5.], 'x', .8, .01, min_points=1)
        self.assertEqual(values, [0., 1., 3.])
        self.assertEqual(unique.call_count, 1)

    def test_single_rc_slice_corrects_selected_rows_without_copying_whole_source(self):
        with patch.object(workers, '_compute_reflection_spectra', wraps=workers._compute_reflection_spectra) as rc:
            with patch.object(workers.np, 'column_stack', wraps=workers.np.column_stack) as stack:
                result = workers.LineWorker(sample_data(), [dict(cut_type='x', c_value=1, epsilon=0)], .8,
                            background_spectra=np.array([10., 20.]), background_scale=2).process()
        np.testing.assert_allclose(result['line_cuts'][0]['spectra'], [[.5, .5], [2., 2.]])
        self.assertEqual(rc.call_args.args[0]['Intensity'].shape, (2, 2))
        self.assertEqual(stack.call_count, 0)

    def test_batch_extracts_each_slice_once_with_shared_y_bounds(self):
        bounds = []
        original_plot = workers.plot_line_cut_spectrogram
        def observe_plot(result, **kwargs):
            bounds.append((result['cut_type'], kwargs['ylim']))
            return original_plot(result, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(workers, 'extract_line_cut', wraps=workers.extract_line_cut) as extract:
                with patch.object(workers, 'plot_line_cut_spectrogram', side_effect=observe_plot):
                    result = workers.BatchLineWorker(sample_data(), ['x', 'y'], 0, directory, .8).process()
            self.assertEqual(result['total_cuts'], 4)
            self.assertEqual(len(list(Path(directory).rglob('*.csv'))), 4)
            self.assertEqual(bounds, [('x', (10., 20.))] * 2 + [('y', (0., 1.))] * 2)
            self.assertEqual(extract.call_count, 4)

    def test_peak_only_refresh_does_not_compute_unused_intensity(self):
        data = sample_data()
        data['energy'] = np.array([1.2, 1.3, 1.4])
        data['Intensity'] = np.column_stack([data['Intensity'], data['Intensity'][:, -1] * 2])
        with patch.object(workers, 'compute_intensity_map', wraps=workers.compute_intensity_map) as intensity:
            result = workers.AnalysisRefreshWorker(data, 1.19, 1.31, 0, .8, 3, 1,
                                                  ['peak_original'], True).process()
        np.testing.assert_allclose(result['peak_map_original']['flat'], [1.4] * 4)
        self.assertEqual(set(result), {'peak_map_original'})
        self.assertEqual(intensity.call_count, 0)

    def test_fixed_only_refresh_does_not_compute_unused_peak_to_peak(self):
        data = sample_data()
        with patch.object(workers, 'compute_rc_peak_to_peak_map', wraps=workers.compute_rc_peak_to_peak_map) as amplitude:
            result = workers.AnalysisRefreshWorker(data, 1.2, 1.3, 0, .8, 3, 1,
                        ['fixed_original'], True, mode='Reflection',
                        background_spectra=np.array([10., 20.]), fixed_energy=1.2).process()
        np.testing.assert_allclose(result['fixed_map_original']['flat'], [5., 3., 2., 1.])
        self.assertEqual(set(result), {'fixed_map_original'})
        self.assertEqual(amplitude.call_count, 0)

    def test_movie_repeats_reuse_rendered_slices_without_changing_video(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(movie, 'render_frame', wraps=movie.render_frame) as render:
                calls = []
                def factory(value):
                    calls.append(value)
                    return cut(value)
                options = movie.MovieOptions(width=420, height=288, fps=10, hold=.1,
                                            direction='pingpong', repeats=3)
                result = movie.export_movie(factory, [0., 1.], Path(directory) / 'repeat.mp4', options)
            reader = imageio_ffmpeg.read_frames(result['path'], pix_fmt='rgb24')
            try:
                metadata = next(reader)
                frames = list(reader)
            finally:
                reader.close()
            self.assertEqual(len(frames), result['info']['frame_count'])
            self.assertEqual(metadata['size'], (420, 288))
            self.assertEqual(render.call_count, 2)
            self.assertEqual(calls, [0., 1.])


class MapFigureReuseTests(SessionMemoryFixture, unittest.TestCase):
    def test_hidden_cached_map_exports_after_its_qt_canvas_is_deleted(self):
        window = self.window()
        self.load(window, self.csv)
        window._refresh_current_map_view()
        self.wait_idle(window)
        hidden = window._current_map_figure()
        window.map_type_combo.setCurrentText('Peak Energy')
        window._refresh_current_map_view()
        self.wait_idle(window)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        path = self.root / 'hidden.png'
        analysis.save_figure_with_axes_size(hidden, str(path), (3., 3.))
        with Image.open(path) as png:
            self.assertEqual(png.mode, 'RGB')
            png.verify()
        window.map_type_combo.setCurrentText('Intensity')
        self.assertIs(window._current_map_figure(), hidden)
        self.assertIs(window.map_plot_tab.canvas.figure, hidden)

    def test_cached_peak_view_redraws_changed_title_on_existing_canvas(self):
        window = self.window()
        self.load(window, self.csv)
        window.map_type_combo.setCurrentText('Peak Energy')
        window._refresh_current_map_view()
        self.wait_idle(window)
        canvas = window.map_plot_tab.canvas
        canvas.draw()
        before = np.asarray(canvas.buffer_rgba()).copy()
        title = window._current_map_figure().axes[0].get_title()
        window.int_min_spin.setValue(1.2)
        window._refresh_current_map_view()
        self.wait_idle(window)
        self.app.processEvents()
        self.assertIs(window.map_plot_tab.canvas, canvas)
        self.assertNotEqual(window._current_map_figure().axes[0].get_title(), title)
        self.assertFalse(np.array_equal(before, np.asarray(canvas.buffer_rgba())))

    def test_rc_preview_corrects_one_frame_instead_of_whole_dataset(self):
        from ui import reflection_workflow
        window = self.save_reflection()
        window.background_scale_check.setChecked(False)
        window.reflection_preview_vbg_spin.setValue(0)
        window.reflection_preview_vtg_spin.setValue(0)
        with patch.object(reflection_workflow, 'compute_rc_spectra', wraps=reflection_workflow.compute_rc_spectra) as rc:
            window._preview_reflection_spectra()
        np.testing.assert_allclose(window.line_plot_tab.current_figure.axes[0].lines[0].get_ydata(),
                                   -1.5 / (11.5 + np.arange(16)))
        self.assertEqual(rc.call_args.args[0].shape, (1, 16))

    def test_energy_edit_updates_raw_background_only_once(self):
        window = self.save_reflection()
        window._preview_reflection_spectra()
        previous = window.line_plot_tab.current_figure
        with patch.object(window, '_refresh_raw_background_plot', wraps=window._refresh_raw_background_plot) as draw:
            window.int_min_spin.setValue(1.16)
            deadline = time.monotonic() + 10
            while window.line_plot_tab.current_figure is previous and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
        self.assertIsNotNone(window.line_plot_tab.current_figure)
        self.assertEqual(draw.call_count, 1)
        self.assertIsNot(window.line_plot_tab.current_figure, previous)

    def test_coordinate_discovery_reuses_settings_and_invalidates_for_tolerance(self):
        from ui import spectral_slices
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        with patch.object(spectral_slices, 'find_all_cut_values', wraps=spectral_slices.find_all_cut_values) as find:
            first = panel._values('x', min_points=2)
            again = panel._values('x', min_points=2)
            panel.epsilon_spin.setValue(.01)
            changed = panel._values('x', min_points=2)
        self.assertEqual(first, [0., 1.])
        self.assertEqual(again, first)
        self.assertEqual(changed, first)
        self.assertEqual(find.call_count, 2)

    def test_refresh_keeps_figure_and_canvas_when_data_is_unchanged(self):
        window = self.window()
        self.load(window, self.csv)
        window._refresh_current_map_view()
        self.wait_idle(window)
        figure = window._current_map_figure()
        canvas = window.map_plot_tab.canvas
        values = window.state.original_map['Z2D'].copy()
        window.map_cmap_combo.setCurrentText('plasma')
        window._refresh_current_map_view()
        self.wait_idle(window)
        np.testing.assert_allclose(window.state.original_map['Z2D'], values, equal_nan=True)
        self.assertEqual(window._current_map_figure().axes[0].collections[0].get_cmap().name, 'plasma')
        self.assertIs(window._current_map_figure(), figure)
        self.assertIs(window.map_plot_tab.canvas, canvas)


class TransportFigureReuseTests(unittest.TestCase):
    setUpClass = classmethod(transport_fixture.TransportUiTests.setUpClass.__func__)
    setUp = transport_fixture.TransportUiTests.setUp
    tearDown = transport_fixture.TransportUiTests.tearDown
    wait = transport_fixture.TransportUiTests.wait
    load = transport_fixture.TransportUiTests.load
    select_map = transport_fixture.TransportUiTests.select_map
    def test_color_changes_keep_mesh_figure_and_canvas(self):
        window = self.load()
        panel = window.transport_panel
        self.select_map(panel)
        figure = panel.map_plot.current_figure
        canvas = panel.map_plot.canvas
        mesh = figure.axes[0].collections[0]
        values = panel.result['Z2D'].copy()
        panel.cmap_combo.setCurrentText('plasma')
        panel.auto_scale.setChecked(False)
        panel.min_edit.setText('0')
        panel.max_edit.setText('5e-9')
        panel._color_changed()
        np.testing.assert_allclose(panel.result['Z2D'], values, equal_nan=True)
        self.assertIs(panel.map_plot.current_figure, figure)
        self.assertIs(panel.map_plot.canvas, canvas)
        self.assertEqual(mesh.get_cmap().name, 'plasma')
        self.assertEqual(mesh.get_clim(), (0., 5e-9))


if __name__ == '__main__':
    unittest.main()
