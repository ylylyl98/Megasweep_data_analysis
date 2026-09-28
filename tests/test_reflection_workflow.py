import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from megasweep_analysis import (
    compute_rc_at_energy_map,
    compute_rc_peak_position,
    compute_rc_peak_to_peak_map,
    compute_rc_spectra,
    estimate_background_scale,
    load_spectral_csv,
    spectral_axes_match,
)
from ui.workers import AnalysisRefreshWorker, BackgroundLoadWorker


class ReflectionWorkflowTests(unittest.TestCase):
    def test_six_significant_digit_headers_match_without_resampling(self):
        precise = np.array([1157.2487, 1047.8650, 999.0455, 899.2866])
        rounded = np.array([1157.25, 1047.86, 999.046, 899.287])
        self.assertTrue(spectral_axes_match(precise, rounded))
        self.assertTrue(spectral_axes_match(rounded, precise))
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "rounded_background.csv")
            pd.DataFrame([[10, 20, 30, 40]], columns=precise.astype(str)).to_csv(path, index=False)
            worker = BackgroundLoadWorker([path], expected_wavelength=rounded)
            logs = []
            worker.log.connect(logs.append)
            result = worker.process()
        np.testing.assert_array_equal(result["background_spectra"], [10, 20, 30, 40])
        self.assertTrue(any("rounding" in message for message in logs))

    def test_rounding_does_not_accept_shift_reordering_or_invalid_axes(self):
        precise = np.array([1157.2487, 1047.8650, 999.0455, 899.2866])
        rounded = np.array([1157.25, 1047.86, 999.046, 899.287])
        for other in (rounded + .02, rounded[::-1], rounded[:-1],
                      [np.inf] * 4, [np.nan] * 4):
            self.assertFalse(spectral_axes_match(precise, other))
        self.assertFalse(spectral_axes_match([1157.2487, 1156.7482], [1157.2527, 1156.7522]))
        self.assertFalse(spectral_axes_match([np.inf], [np.inf]))

    def test_rounding_at_power_of_ten_uses_finer_lower_interval(self):
        self.assertFalse(spectral_axes_match([1000.0, 1001.23], [999.996, 1001.234]))
        self.assertTrue(spectral_axes_match([1000.0, 1001.23], [999.9995, 1001.234]))

    def test_background_mismatch_reports_file_channel_and_difference(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "wrong_background.csv")
            pd.DataFrame([[10, 20]], columns=["1157.2487", "1156.7482"]).to_csv(path, index=False)
            worker = BackgroundLoadWorker([path], expected_wavelength=np.array([1157.25, 1156.80]))
            with self.assertRaises(ValueError) as raised:
                worker.process()
        message = str(raised.exception)
        self.assertIn("wrong_background.csv", message)
        self.assertIn("channel 2", message)
        self.assertIn("0.0518", message)

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

    def test_two_side_windows_recover_global_background_scale(self):
        energy = np.array([1.50, 1.52, 1.54, 1.56, 1.58, 1.60, 1.62])
        background = np.full(energy.shape, 100.0)
        sample = np.array([60.0, 60.0, 60.0, 66.0, 60.0, 60.0, 60.0])

        scale, info = estimate_background_scale(
            sample,
            background,
            energy,
            windows=[(1.50, 1.54), (1.58, 1.62)],
        )
        rc = compute_rc_spectra(
            sample.reshape(1, -1),
            background,
            background_scale=scale,
        )[0]

        self.assertAlmostEqual(0.6, scale)
        self.assertEqual(6, info["channel_count"])
        np.testing.assert_allclose(rc[[0, 1, 2, 4, 5, 6]], 0.0)
        self.assertAlmostEqual(0.1, rc[3])

    def test_peak_to_peak_uses_only_selected_energy_window(self):
        energy = np.array([1.0, 1.1, 1.2, 1.3])
        rc = np.array([
            [-5.0, -0.2, 0.4, 9.0],
            [7.0, 0.5, -0.5, -8.0],
        ])
        values = compute_rc_peak_to_peak_map(rc, energy, 1.1, 1.2)
        np.testing.assert_allclose(values, [0.6, 1.0])

    def test_fixed_energy_rc_map_interpolates_each_spectrum(self):
        energy = np.array([1.0, 1.1, 1.2])
        rc = np.array([
            [0.0, 0.2, 0.6],
            [1.0, 0.0, -1.0],
        ])

        values = compute_rc_at_energy_map(rc, energy, 1.15)

        np.testing.assert_allclose(values, [0.4, -0.5])

    def test_fixed_energy_rc_map_rejects_energy_outside_data(self):
        with self.assertRaisesRegex(ValueError, "outside the data range"):
            compute_rc_at_energy_map(
                np.array([[0.1, 0.2]]),
                np.array([1.0, 1.1]),
                1.2,
            )

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

    def test_peak_position_can_select_peak_or_dip(self):
        energy = np.linspace(1.0, 2.0, 201)
        spectrum = (
            np.exp(-((energy - 1.30) / 0.03) ** 2)
            - 2.0 * np.exp(-((energy - 1.70) / 0.03) ** 2)
        )

        peak_energy, _ = compute_rc_peak_position(
            energy,
            spectrum,
            1.1,
            1.9,
            sg_window=11,
            sg_poly=3,
            feature_mode="peak",
        )
        dip_energy, _ = compute_rc_peak_position(
            energy,
            spectrum,
            1.1,
            1.9,
            sg_window=11,
            sg_poly=3,
            feature_mode="dip",
        )

        self.assertAlmostEqual(1.30, peak_energy, places=2)
        self.assertAlmostEqual(1.70, dip_energy, places=2)

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

    def test_reflection_worker_builds_fixed_energy_rc_map(self):
        energy = np.array([1.0, 1.1, 1.2])
        background = np.full(3, 10.0)
        rc = np.array([
            [0.0, 0.2, 0.6],
            [1.0, 0.0, -1.0],
            [0.2, 0.4, 0.8],
            [-0.2, -0.4, -0.8],
        ])
        data = {
            "x_data": np.array([0.0, 0.0, 1.0, 1.0]),
            "y_data": np.array([0.0, 1.0, 0.0, 1.0]),
            "energy": energy,
            "Intensity": 0.6 * background * (1.0 + rc),
            "axis_space": "generic",
        }

        result = AnalysisRefreshWorker(
            data,
            min_energy=1.0,
            max_energy=1.2,
            baseline=0.0,
            ratio=1.0,
            sg_window=3,
            sg_poly=1,
            tasks=["fixed_original"],
            tg_is_y=True,
            mode="Reflection",
            background_spectra=background,
            fixed_energy=1.15,
            background_scale=0.6,
        ).process()

        np.testing.assert_allclose(
            result["fixed_map_original"]["flat"],
            [0.4, -0.5, 0.6, -0.6],
        )
        self.assertEqual(1.15, result["fixed_map_original"]["fixed_energy"])
        self.assertEqual(
            0.6,
            result["fixed_map_original"]["background_scale"],
        )


if __name__ == "__main__":
    unittest.main()
