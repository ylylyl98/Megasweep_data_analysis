import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from matplotlib.collections import PathCollection, QuadMesh
from PIL import Image

from megasweep_analysis import build_map_payload, plot_map, save_figure


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


if __name__ == "__main__":
    unittest.main()
