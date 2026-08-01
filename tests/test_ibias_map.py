import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from megasweep_analysis import (
    find_ibias_column,
    find_vbias_column,
    load_megasweep_csv,
)
from ui.workers import AnalysisRefreshWorker


class IbiasMapTests(unittest.TestCase):
    def test_finds_measured_ibias_column_without_using_setpoint(self):
        columns = [
            "Doping_axis_a_set",
            "Vbias_axis_b_set",
            "Ibias_set",
            "Ibias_A",
            "700.000",
        ]

        self.assertEqual("Ibias_A", find_ibias_column(columns))

    def test_finds_measured_vbias_column_without_using_setpoint(self):
        columns = [
            "Vbias_axis_b_set",
            "Vbias_set",
            "Vbias_meas",
            "Ibias_A",
        ]

        self.assertEqual("Vbias_meas", find_vbias_column(columns))

    def test_csv_loader_exposes_ibias_values(self):
        frame = pd.DataFrame(
            {
                "Doping_axis_a_set": [-2.0, -2.0, -1.0, -1.0],
                "Vbias_axis_b_set": [0.0, -0.1, 0.0, -0.1],
                "Vbias_meas": [0.0, -0.09, 0.0, -0.095],
                "Ibias_A": [1e-9, 2e-9, 3e-9, 4e-9],
                "700.000": [10.0, 11.0, 12.0, 13.0],
                "701.000": [20.0, 21.0, 22.0, 23.0],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "measurement.csv")
            frame.to_csv(path, index=False)
            data = load_megasweep_csv(
                path,
                x_col="Doping_axis_a_set",
                y_col="Vbias_axis_b_set",
            )

        self.assertEqual("Ibias_A", data["ibias_name"])
        np.testing.assert_allclose(data["ibias_data"], [1e-9, 2e-9, 3e-9, 4e-9])
        self.assertEqual("Vbias_meas", data["vbias_name"])
        np.testing.assert_allclose(
            data["vbias_data"],
            [0.0, -0.09, 0.0, -0.095],
        )

    def test_ibias_map_does_not_require_reflection_background(self):
        data = {
            "x_data": np.array([-2.0, -2.0, -1.0, -1.0]),
            "y_data": np.array([0.0, -0.1, 0.0, -0.1]),
            "axis_space": "generic",
            "ibias_name": "Ibias_A",
            "ibias_data": np.array([1e-9, 2e-9, 3e-9, 4e-9]),
        }
        result = AnalysisRefreshWorker(
            data=data,
            min_energy=1.6,
            max_energy=1.8,
            baseline=0.0,
            ratio=1.0,
            sg_window=5,
            sg_poly=2,
            tasks=["ibias_original"],
            tg_is_y=True,
            mode="Reflection",
            background_spectra=None,
        ).process()

        map_data = result["ibias_map_original"]
        self.assertEqual("original", map_data["target_axes"])
        self.assertEqual("Ibias_A", map_data["source_column"])
        np.testing.assert_allclose(
            np.sort(np.asarray(map_data["Z2D"]).reshape(-1)),
            [1e-9, 2e-9, 3e-9, 4e-9],
        )

    def test_resistance_map_uses_vbias_over_ibias_and_blanks_zero_current(self):
        data = {
            "x_data": np.array([-2.0, -2.0, -1.0, -1.0]),
            "y_data": np.array([0.0, -0.1, 0.0, -0.1]),
            "axis_space": "generic",
            "ibias_name": "Ibias_A",
            "ibias_data": np.array([1e-9, 0.0, 2e-9, -4e-9]),
            "vbias_name": "Vbias_meas",
            "vbias_data": np.array([0.0, -0.1, 0.0, -0.1]),
        }
        result = AnalysisRefreshWorker(
            data=data,
            min_energy=1.6,
            max_energy=1.8,
            baseline=0.0,
            ratio=1.0,
            sg_window=5,
            sg_poly=2,
            tasks=["resistance_original"],
            tg_is_y=True,
            mode="Reflection",
            background_spectra=None,
        ).process()

        map_data = result["resistance_map_original"]
        resistance = np.asarray(map_data["Z2D"]).reshape(-1)
        self.assertEqual("Vbias_meas", map_data["vbias_column"])
        self.assertEqual("Ibias_A", map_data["ibias_column"])
        self.assertEqual(1, np.count_nonzero(np.isnan(resistance)))
        np.testing.assert_allclose(
            np.sort(resistance[np.isfinite(resistance)]),
            [0.0, 0.0, 25_000_000.0],
        )


if __name__ == "__main__":
    unittest.main()
