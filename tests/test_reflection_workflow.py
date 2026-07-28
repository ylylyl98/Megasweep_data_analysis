import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from megasweep_analysis import (
    compute_rc_peak_position,
    compute_rc_peak_to_peak_map,
    compute_rc_spectra,
    load_spectral_csv,
    spectral_axes_match,
)
from ui.workers import AnalysisRefreshWorker, BackgroundLoadWorker


class ReflectionWorkflowTests(unittest.TestCase):
    def test_background_loader_ignores_primary_sweep_metadata(self):
        frame = pd.DataFrame({
            "Vbg_set": [0.0, 0.0],
            "Vtg_set": [0.0, 0.0],
            "Ibias": [1e-9, 2e-9],
            "657.9571": [10.0, 14.0],
            "658.0202": [20.0, 24.0],
        })
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "background.csv")
            frame.to_csv(path, index=False)
            result = BackgroundLoadWorker(
                [path],
                average_mode="all_frames",
                expected_wavelength=np.array([657.9570, 658.0200]),
            ).process()

        np.testing.assert_allclose(result["background_spectra"], [12.0, 22.0])
        self.assertEqual(2, result["spectrum_count"])

    def test_spectral_only_loader_uses_numeric_headers(self):
        frame = pd.DataFrame({
            "Different_metadata": [123.0],
            "700.0": [50.0],
            "701.0": [60.0],
        })
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "reference.csv")
            frame.to_csv(path, index=False)
            data = load_spectral_csv(path)

        np.testing.assert_allclose(data["wavelength"], [700.0, 701.0])
        np.testing.assert_allclose(data["Intensity"], [[50.0, 60.0]])

    def test_spectral_axis_matching_allows_header_rounding_only(self):
        self.assertTrue(
            spectral_axes_match(
                np.array([657.9571, 658.0202]),
                np.array([657.9570, 658.0200]),
            )
        )
        self.assertFalse(
            spectral_axes_match(
                np.array([657.9571, 658.0202]),
                np.array([657.9571, 658.1000]),
            )
        )

    def test_rc_formula_is_data_minus_background_over_background(self):
        intensity = np.array([[12.0, 18.0], [8.0, 30.0]])
        background = np.array([10.0, 20.0])
        rc = compute_rc_spectra(intensity, background)
        np.testing.assert_allclose(rc, [[0.2, -0.1], [-0.2, 0.5]])

    def test_peak_to_peak_uses_only_selected_energy_window(self):
        energy = np.array([1.0, 1.1, 1.2, 1.3])
        rc = np.array([
            [-5.0, -0.2, 0.4, 9.0],
            [7.0, 0.5, -0.5, -8.0],
        ])
        values = compute_rc_peak_to_peak_map(rc, energy, 1.1, 1.2)
        np.testing.assert_allclose(values, [0.6, 1.0])

    def test_peak_position_uses_only_selected_energy_window(self):
        energy = np.linspace(1.0, 2.0, 201)
        spectrum = (
            np.exp(-((energy - 1.35) / 0.03) ** 2)
            + 2.0 * np.exp(-((energy - 1.75) / 0.03) ** 2)
        )
        peak_energy, _ = compute_rc_peak_position(
            energy,
            spectrum,
            1.2,
            1.5,
            sg_window=11,
            sg_poly=3,
        )
        self.assertAlmostEqual(1.35, peak_energy, places=2)

    def test_reflection_map_worker_uses_rc_peak_to_peak_as_z(self):
        energy = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
        background = np.full(5, 10.0)
        rc = np.array([
            [9.0, -0.2, 0.4, 0.0, -9.0],
            [8.0, 0.5, -0.5, 0.2, -8.0],
            [7.0, -0.1, 0.2, 0.6, -7.0],
            [6.0, 0.9, 0.1, -0.3, -6.0],
        ])
        data = {
            "x_data": np.array([0.0, 0.0, 1.0, 1.0]),
            "y_data": np.array([0.0, 1.0, 0.0, 1.0]),
            "energy": energy,
            "Intensity": background * (1.0 + rc),
            "axis_space": "generic",
        }
        result = AnalysisRefreshWorker(
            data,
            min_energy=1.1,
            max_energy=1.3,
            baseline=0.0,
            ratio=1.0,
            sg_window=3,
            sg_poly=1,
            tasks=["intensity_original", "peak_original"],
            tg_is_y=True,
            mode="Reflection",
            background_spectra=background,
        ).process()

        np.testing.assert_allclose(
            result["original_map"]["flat"],
            [0.6, 1.0, 0.7, 1.2],
        )
        self.assertIn("peak_map_original", result)


if __name__ == "__main__":
    unittest.main()
