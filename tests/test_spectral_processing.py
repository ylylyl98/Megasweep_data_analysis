import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from ui.workers import LineWorker, BatchLineWorker


class SpectralProcessingTests(unittest.TestCase):
    def data(self):
        energy = np.array([2.1, 1.9, 1.75, 1.5, 1.2])
        return dict(energy=energy, x_data=np.array([0., 0.]), y_data=np.array([1., 2.]),
                    x_name='Field (T)', y_name='Temperature (K)', axis_space='generic',
                    Intensity=np.array([3*energy**2 + 2*energy + 1, -2*energy**2 + energy]))

    def test_derivative_uses_energy_spacing_and_preserves_descending_channels(self):
        data = self.data()
        original = data['Intensity'].copy()
        result = LineWorker(data, [dict(cut_type='x', c_value=0, epsilon=0)], 1,
                            exact_coordinates=True, spectral_processing='second_derivative',
                            derivative_window=5).process()['line_cuts'][0]
        np.testing.assert_allclose(result['spectra'], [[6]*5, [-4]*5], atol=1e-11)
        np.testing.assert_array_equal(result['energy'], data['energy'])
        np.testing.assert_array_equal(data['Intensity'], original)
        self.assertIn('eV²', result['signal_label'])

    def test_rc_derivative_is_after_background_normalization(self):
        data = self.data()
        rc = data['Intensity'].copy()
        background = np.array([10., 20., 30., 40., 50.])
        data['Intensity'] = (rc + 1) * (2 * background)
        result = LineWorker(data, [dict(cut_type='x', c_value=0, epsilon=0)], 1,
                            background_spectra=background, background_scale=2,
                            spectral_processing='second_derivative', derivative_window=5).process()['line_cuts'][0]
        np.testing.assert_allclose(result['spectra'], [[6]*5, [-4]*5], atol=1e-11)
        self.assertIn('RC', result['signal_label'])

    def test_batch_derivative_exports_values_and_identifies_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            BatchLineWorker(self.data(), ['x'], 0, directory, 1, exact_coordinates=True,
                            spectral_processing='second_derivative', derivative_window=5).process()
            csv = next(Path(directory).rglob('*.csv'))
            self.assertIn('d2dE2_w5', csv.name)
            frame = pd.read_csv(csv)
            np.testing.assert_allclose(frame.iloc[:, 1:6], [[6]*5, [-4]*5], atol=1e-11)
            self.assertEqual(frame['processing'].iloc[0], 'second_derivative')
            self.assertEqual(frame['derivative_window'].iloc[0], 5)

    def test_invalid_derivative_window_is_rejected(self):
        for window in (2, 4, 7):
            with self.subTest(window=window), self.assertRaisesRegex(ValueError, 'window'):
                LineWorker(self.data(), [dict(cut_type='x', c_value=0, epsilon=0)], 1,
                           spectral_processing='second_derivative', derivative_window=window).process()


if __name__ == '__main__':
    unittest.main()
