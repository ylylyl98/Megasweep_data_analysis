import os
import tempfile
import unittest

from megasweep_analysis import (
    dataset_output_folder_name,
    resolve_dataset_output_dir,
)


class OutputRoutingTests(unittest.TestCase):
    def test_each_csv_gets_an_independent_results_subfolder(self):
        with tempfile.TemporaryDirectory() as base_dir:
            first = resolve_dataset_output_dir(
                base_dir,
                os.path.join(base_dir, "sample_a.csv"),
            )
            second = resolve_dataset_output_dir(
                base_dir,
                os.path.join(base_dir, "sample_b.csv"),
            )

        self.assertEqual(os.path.join(base_dir, "sample_a_outputs"), first)
        self.assertEqual(os.path.join(base_dir, "sample_b_outputs"), second)
        self.assertNotEqual(first, second)

    def test_empty_base_uses_processed_csv_parent(self):
        csv_path = os.path.join("measurement_folder", "sample.csv")

        result = resolve_dataset_output_dir("", csv_path)

        self.assertEqual(
            os.path.join(
                os.path.dirname(os.path.abspath(csv_path)),
                "sample_outputs",
            ),
            result,
        )

    def test_existing_dataset_folder_is_not_nested_again(self):
        base_dir = os.path.join("results", "sample_outputs")

        result = resolve_dataset_output_dir(base_dir, "sample.csv")

        self.assertEqual(os.path.abspath(base_dir), result)

    def test_missing_csv_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "processed CSV path"):
            resolve_dataset_output_dir("results", "")

    def test_long_measurement_name_is_preserved_in_dataset_folder(self):
        csv_name = (
            "YZD364~D-2to+3_101pts_Vb0to-0p2_41pts_r1~E+30~"
            "730nm1.000uW~700nm_0p1sx20~0Tpanx_biasonMo.csv"
        )

        first = dataset_output_folder_name(csv_name)
        second = dataset_output_folder_name(csv_name)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("YZD364~D-2to+3"))
        self.assertTrue(first.endswith("_outputs"))


if __name__ == "__main__":
    unittest.main()
