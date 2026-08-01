import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from matplotlib.collections import PathCollection, QuadMesh
from PIL import Image

from megasweep_analysis import (
    build_map_payload,
    plot_map,
    save_figure,
    save_figure_with_axes_size,
)
from ui.workers import AnalysisRefreshWorker


class MapRenderingTests(unittest.TestCase):
    def test_regular_grid_renders_one_quadmesh_cell_per_measurement(self):
        payload = build_map_payload(
            np.repeat([0.0, 1.0], 3),
            np.tile([0.0, 1.0, 2.0], 2),
            np.arange(6, dtype=float),
        )
        figure, axis = plot_map(
            payload["X2D"],
            payload["Y2D"],
            payload["Z2D"],
            title="RC Peak-to-Peak | 1.680–1.820 eV",
        )

        meshes = [
            collection
            for collection in axis.collections
            if isinstance(collection, QuadMesh)
        ]
        self.assertEqual(1, len(meshes))
        self.assertEqual(6, np.asarray(meshes[0].get_array()).size)
        self.assertEqual(
            "RC Peak-to-Peak | 1.680–1.820 eV",
            axis.get_title(),
        )
        figure.clear()

    def test_irregular_map_uses_discrete_square_samples(self):
        figure, axis = plot_map(
            np.array([0.0, 0.7, 1.8, 2.2]),
            np.array([0.0, 1.1, 0.4, 1.8]),
            np.array([1.0, 2.0, 3.0, 4.0]),
        )

        points = [
            collection
            for collection in axis.collections
            if isinstance(collection, PathCollection)
        ]
        self.assertEqual(1, len(points))
        self.assertEqual(4, points[0].get_offsets().shape[0])
        figure.clear()

    def test_skipped_grid_points_render_as_masked_full_size_cells(self):
        x_full = np.repeat([0.0, 1.0, 2.0], 3)
        y_full = np.tile([0.0, 1.0, 2.0], 3)
        keep = ~((x_full == 1.0) & (y_full == 1.0))
        payload = build_map_payload(
            x_full[keep],
            y_full[keep],
            np.arange(8, dtype=float),
        )

        self.assertEqual("masked", payload["grid_kind"])
        self.assertEqual((3, 3), payload["Z2D"].shape)
        self.assertEqual(1, payload["missing_count"])
        self.assertTrue(np.isnan(payload["Z2D"][1, 1]))

        figure, axis = plot_map(
            payload["X2D"],
            payload["Y2D"],
            payload["Z2D"],
        )
        meshes = [
            collection
            for collection in axis.collections
            if isinstance(collection, QuadMesh)
        ]
        points = [
            collection
            for collection in axis.collections
            if isinstance(collection, PathCollection)
        ]
        self.assertEqual(1, len(meshes))
        self.assertEqual(9, np.asarray(meshes[0].get_array()).size)
        self.assertEqual(1, np.ma.count_masked(meshes[0].get_array()))
        self.assertEqual([], points)
        figure.clear()

    def test_transformed_map_preserves_skipped_gate_grid_topology(self):
        x_full = np.repeat([-1.0, 0.0, 1.0], 3)
        y_full = np.tile([-1.0, 0.0, 1.0], 3)
        keep = ~((x_full == 0.0) & (y_full == 0.0))
        data = {
            "x_data": x_full[keep],
            "y_data": y_full[keep],
            "energy": np.array([1.0, 1.1]),
            "Intensity": np.arange(16, dtype=float).reshape(8, 2),
            "axis_space": "gate",
        }

        result = AnalysisRefreshWorker(
            data=data,
            min_energy=0.99,
            max_energy=1.11,
            baseline=0.0,
            ratio=1.0,
            sg_window=3,
            sg_poly=1,
            tasks=["intensity_transformed"],
            tg_is_y=True,
            mode="PL",
        ).process()

        transformed = result["transformed_map"]
        self.assertEqual("masked", transformed["grid_kind"])
        self.assertEqual((3, 3), transformed["Z2D"].shape)
        self.assertEqual(1, transformed["missing_count"])
        self.assertTrue(np.isnan(transformed["Z2D"][1, 1]))

    def test_png_export_is_powerpoint_compatible_rgb(self):
        figure, _ = plot_map(
            np.array([[0.0, 0.0], [1.0, 1.0]]),
            np.array([[0.0, 1.0], [0.0, 1.0]]),
            np.array([[1.0, 2.0], [3.0, 4.0]]),
        )
        with TemporaryDirectory() as folder:
            path = Path(folder) / "map.png"
            save_figure(figure, str(path))

            with Image.open(path) as exported:
                exported.verify()
            with Image.open(path) as exported:
                self.assertEqual("PNG", exported.format)
                self.assertEqual("RGB", exported.mode)

        figure.clear()

    def test_map_export_fixes_inner_axes_size_and_restores_live_figure(self):
        figure, axis = plot_map(
            np.array([[0.0, 0.0], [1.0, 1.0]]),
            np.array([[0.0, 1.0], [0.0, 1.0]]),
            np.array([[1.0, 2.0], [3.0, 4.0]]),
        )
        original_size = np.asarray(figure.get_size_inches(), dtype=float)
        original_positions = {
            item: np.asarray(item.get_position().bounds, dtype=float)
            for item in figure.axes
        }
        colorbar_axis = figure.axes[1]
        original_title_size = axis.title.get_fontsize()
        original_x_tick_size = axis.get_xticklabels()[0].get_fontsize()
        original_colorbar_tick_size = (
            colorbar_axis.get_yticklabels()[0].get_fontsize()
        )
        original_colorbar_box_aspect = colorbar_axis.get_box_aspect()
        captured = {}

        def capture_export(export_figure, _path, dpi=300):
            position = axis.get_position()
            colorbar_position = colorbar_axis.get_position()
            figure_size = export_figure.get_size_inches()
            captured["dpi"] = dpi
            captured["axes_size"] = (
                position.width * figure_size[0],
                position.height * figure_size[1],
            )
            captured["colorbar_size"] = (
                colorbar_position.width * figure_size[0],
                colorbar_position.height * figure_size[1],
            )
            captured["colorbar_gap"] = (
                colorbar_position.x0 - position.x1
            ) * figure_size[0]
            captured["title_size"] = axis.title.get_fontsize()
            captured["x_tick_size"] = axis.get_xticklabels()[0].get_fontsize()
            captured["colorbar_tick_size"] = (
                colorbar_axis.get_yticklabels()[0].get_fontsize()
            )
            captured["colorbar_box_aspect"] = colorbar_axis.get_box_aspect()

        with patch("megasweep_analysis.save_figure", side_effect=capture_export):
            save_figure_with_axes_size(
                figure,
                "unused.png",
                axes_size=(3.0, 3.0),
                dpi=300,
                axis=axis,
            )

        np.testing.assert_allclose(captured["axes_size"], [3.0, 3.0])
        np.testing.assert_allclose(captured["colorbar_size"], [0.18, 3.0])
        self.assertAlmostEqual(0.20, captured["colorbar_gap"])
        self.assertEqual(300, captured["dpi"])
        self.assertEqual(12.0, captured["title_size"])
        self.assertEqual(10.0, captured["x_tick_size"])
        self.assertEqual(10.0, captured["colorbar_tick_size"])
        self.assertIsNone(captured["colorbar_box_aspect"])
        np.testing.assert_allclose(figure.get_size_inches(), original_size)
        for item, original_position in original_positions.items():
            np.testing.assert_allclose(item.get_position().bounds, original_position)
        self.assertEqual(original_title_size, axis.title.get_fontsize())
        self.assertEqual(
            original_x_tick_size,
            axis.get_xticklabels()[0].get_fontsize(),
        )
        self.assertEqual(
            original_colorbar_tick_size,
            colorbar_axis.get_yticklabels()[0].get_fontsize(),
        )
        self.assertEqual(
            original_colorbar_box_aspect,
            colorbar_axis.get_box_aspect(),
        )

        figure.clear()


if __name__ == "__main__":
    unittest.main()
