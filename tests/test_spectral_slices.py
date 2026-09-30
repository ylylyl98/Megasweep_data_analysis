import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from megasweep_analysis import extract_line_cut, find_all_cut_values
from ui.workers import LineWorker, BatchLineWorker


def sample_data():
    return dict(x_data=np.array([1., 0., 1., 0.]),
                y_data=np.array([20., 20., 10., 10.]),
                Intensity=np.array([[60., 120.], [40., 80.], [30., 60.], [20., 40.]]),
                energy=np.array([1.2, 1.3]), axis_space='generic',
                x_name='Field (T)', y_name='Temperature (K)')


class SpectralSliceTests(unittest.TestCase):
    def test_original_cuts_preserve_spectra_and_sort_varying_axis(self):
        data = sample_data()
        for kind, value, axis, spectra, label in (
            ('x', 1., [10., 20.], [[30., 60.], [60., 120.]], 'Temperature (K)'),
            ('y', 10., [0., 1.], [[20., 40.], [30., 60.]], 'Field (T)'),
        ):
            with self.subTest(kind=kind):
                result = LineWorker(data, [dict(cut_type=kind, c_value=value, epsilon=0)], .8).process()
                cut = result['line_cuts'][0]
                np.testing.assert_array_equal(cut['axis_values'], axis)
                np.testing.assert_array_equal(cut['spectra'], spectra)
                self.assertEqual(cut['axis_label'], label)
                self.assertEqual(cut['coordinate_space'], 'original')

    def test_reflection_slice_applies_background_scale(self):
        result = LineWorker(sample_data(), [dict(cut_type='x', c_value=1, epsilon=0)], .8,
                            background_spectra=np.array([10., 20.]), background_scale=2).process()
        np.testing.assert_allclose(result['line_cuts'][0]['spectra'], [[.5, .5], [2., 2.]])

    def test_transformed_cuts_still_use_gate_formula_or_loaded_de_axes(self):
        data = sample_data()
        data.update(axis_space='gate', x_name='Vbg', y_name='Vtg',
                    x_data=np.array([0., 1., 2.]), y_data=np.array([2., 1., 0.]),
                    Intensity=np.array([[10., 20.], [30., 40.], [50., 60.]]))
        spec = [dict(cut_type='doping', c_value=2, epsilon=0)]
        gate = LineWorker(data, spec, 1).process()['line_cuts'][0]
        np.testing.assert_array_equal(gate['axis_values'], [-2, 0, 2])
        np.testing.assert_array_equal(gate['spectra'], [[50, 60], [30, 40], [10, 20]])
        data.update(axis_space='transformed', x_name='Doping', y_name='Efield',
                    x_data=np.array([2., 2., 2.]), y_data=np.array([2., 0., -2.]))
        loaded = LineWorker(data, spec, .8).process()['line_cuts'][0]
        np.testing.assert_array_equal(loaded['spectra'], gate['spectra'])

    def test_raw_axes_do_not_merge_small_setpoints_or_apply_gate_noise_floor(self):
        x = np.array([0, 1e-7, 0, 1e-7])
        y = np.array([0, 0, 1e-10, 1e-10])
        raw = np.column_stack([x, y, [1, 2, 3, 4]])
        values = find_all_cut_values(x, y, 'x', .8, 0, axis_space='generic')
        np.testing.assert_array_equal(values, [0, 1e-7])
        cut = extract_line_cut(raw, x, y, [1.2], cut_type='x', c_value=1e-7,
                               epsilon=0, axis_space='generic')
        np.testing.assert_array_equal(cut['axis_values'], [0, 1e-10])
        np.testing.assert_array_equal(cut['spectra'].ravel(), [2, 4])

    def test_raw_discovery_requires_distinct_finite_varying_points(self):
        values = find_all_cut_values([0, 0, 1, 1, 2, 2], [10, 10, 10, 20, 10, np.nan],
                                     'x', .8, 0, axis_space='generic')
        self.assertEqual(values, [1.])

    def test_exact_transformed_slice_does_not_average_nearby_setpoints(self):
        data = sample_data()
        data.update(axis_space='transformed', x_name='Doping (V)', y_name='Efield (V)',
                    x_data=np.array([0., .0005, 0., .0005]), y_data=np.array([1., 1., 2., 2.]))
        values = find_all_cut_values(data['x_data'], data['y_data'], 'doping', .8, 0,
                                     axis_space='transformed', x_axis_name='Doping (V)',
                                     y_axis_name='Efield (V)', exact_coordinates=True)
        self.assertEqual(values, [0., .0005])
        cut = LineWorker(data, [dict(cut_type='doping', c_value=0., epsilon=0)], .8,
                         exact_coordinates=True).process()['line_cuts'][0]
        np.testing.assert_array_equal(cut['spectra'], [[60., 120.], [30., 60.]])

    def test_raw_tolerance_keeps_nearest_sample_for_each_varying_value(self):
        x, y = np.array([1.01, 1.001, .99]), np.array([20., 20., 10.])
        cut = extract_line_cut(np.column_stack([x, y, [1., 2., 3.]]), x, y, [1.2],
                               cut_type='x', c_value=1, epsilon=.02, axis_space='generic')
        np.testing.assert_array_equal(cut['spectra'].ravel(), [3., 2.])

    def test_batch_original_exports_both_directions_with_axis_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            result = BatchLineWorker(sample_data(), ['x', 'y'], 0, directory, .8).process()
            self.assertEqual(result['total_cuts'], 4)
            self.assertEqual(len(result['saved_files']), 8)
            csvs = list(Path(directory).rglob('*.csv'))
            self.assertEqual(len(csvs), 4)
            frame = pd.read_csv(next(p for p in csvs if 'x_fixed' in str(p)))
            self.assertEqual(frame.columns[0], 'Temperature (K)')
            self.assertIn('fixed_Field (T)', frame.columns)
            self.assertTrue(any('Field' in p.name for p in csvs))


if __name__ == '__main__':
    unittest.main()
