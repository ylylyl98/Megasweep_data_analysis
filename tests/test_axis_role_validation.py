import unittest

from megasweep_analysis import classify_axis_role, validate_axis_selection


class AxisRoleValidationTests(unittest.TestCase):
    def test_classifies_realistic_gate_axis_names(self):
        self.assertEqual("tg", classify_axis_role("vtg_axis_a_set"))
        self.assertEqual("bg", classify_axis_role("vbg_axis_b_set"))

    def test_classifies_realistic_transformed_axis_names(self):
        self.assertEqual("doping", classify_axis_role("doping_set"))
        self.assertEqual("efield", classify_axis_role("efield_set"))

    def test_accepts_expected_raw_gate_assignment(self):
        result = validate_axis_selection("vbg_axis_b_set", "vtg_axis_a_set")
        self.assertTrue(result["ok"])
        self.assertEqual("raw_gate", result["mode"])

    def test_blocks_swapped_raw_gate_assignment(self):
        result = validate_axis_selection("vtg_axis_a_set", "vbg_axis_b_set")
        self.assertFalse(result["ok"])
        self.assertEqual("swapped_raw_gate", result["mode"])

    def test_accepts_expected_transformed_assignment(self):
        result = validate_axis_selection("doping_set", "efield_set")
        self.assertTrue(result["ok"])
        self.assertEqual("transformed", result["mode"])

    def test_blocks_swapped_transformed_assignment(self):
        result = validate_axis_selection("efield_set", "doping_set")
        self.assertFalse(result["ok"])
        self.assertEqual("swapped_transformed", result["mode"])

    def test_allows_unknown_custom_assignment_with_warning_mode(self):
        result = validate_axis_selection("axis_0", "axis_1")
        self.assertTrue(result["ok"])
        self.assertEqual("unknown", result["mode"])


if __name__ == "__main__":
    unittest.main()
