import math
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from seer_demo.fastwam.rollout import (
    CANONICAL_POLICY_PROMPT,
    derive_phase,
    validate_policy_action,
)
from seer_demo.fastwam.scene_variant import ASSETS, SCENE_VARIANT_ID


class FastWamRolloutTests(unittest.TestCase):
    def test_variant_contains_physical_red_apple_and_yellow_plate_goal(self):
        apple_path = ASSETS / "red_apple.xml"
        plate_path = ASSETS / "yellow_plate.xml"
        apple = ET.parse(apple_path)
        plate = ET.parse(plate_path)
        apple_text = apple_path.read_text(encoding="utf-8")
        plate_text = plate_path.read_text(encoding="utf-8")
        bddl = (ASSETS / "put_red_apple_on_yellow_plate.bddl").read_text(
            encoding="utf-8"
        )

        self.assertTrue(apple.findall(".//geom[@type='sphere']"))
        self.assertIn("0.80 0.03 0.02 1", apple_text)
        self.assertTrue(plate.findall(".//geom[@type='cylinder']"))
        self.assertIn("0.95 0.70 0.04 1", plate_text)
        self.assertIn("red_apple_1 - red_apple", bddl)
        self.assertIn("yellow_plate_1 - yellow_plate", bddl)
        self.assertIn("(On red_apple_1 yellow_plate_1)", bddl)
        self.assertEqual(SCENE_VARIANT_ID, "libero_goal_8_apple_plate_visual_v1")

    def test_variant_preserves_official_task_structure_and_policy_prompt(self):
        bddl = (ASSETS / "put_red_apple_on_yellow_plate.bddl").read_text(
            encoding="utf-8"
        )
        for fixture in ("main_table", "wooden_cabinet_1", "flat_stove_1", "wine_rack_1"):
            self.assertIn(fixture, bddl)
        for distractor in ("cream_cheese_1", "wine_bottle_1"):
            self.assertIn(distractor, bddl)
        for region in (
            "plate_region",
            "akita_black_bowl_region",
            "wine_bottle_region",
            "cream_cheese_region",
            "cabinet_region",
            "stove_region",
            "wine_rack_region",
        ):
            self.assertIn(region, bddl)
        self.assertIn("(:language Put the bowl on the plate)", bddl)
        self.assertEqual(CANONICAL_POLICY_PROMPT, "Put the bowl on the plate")

    def test_policy_action_requires_finite_bounded_seven_values(self):
        self.assertEqual(validate_policy_action([0.0] * 7), (0.0,) * 7)
        for value in (
            [0.0] * 6,
            [0.0] * 6 + [math.nan],
            [0.0] * 6 + [1.1],
            [0.0] * 6 + [True],
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_policy_action(value)

    def test_phase_is_derived_only_from_measured_observation(self):
        initial = {
            "apple_lift_m": 0.0,
            "plate_xy_error_m": 0.35,
            "gripper_closed": False,
            "official_success": False,
        }
        self.assertEqual(derive_phase(initial), "ARM-OP-01")
        self.assertEqual(
            derive_phase({**initial, "gripper_closed": True}), "ARM-OP-02"
        )
        self.assertEqual(
            derive_phase({**initial, "gripper_closed": True, "apple_lift_m": 0.05}),
            "ARM-OP-03",
        )
        self.assertEqual(
            derive_phase(
                {
                    **initial,
                    "gripper_closed": True,
                    "apple_lift_m": 0.05,
                    "plate_xy_error_m": 0.05,
                }
            ),
            "ARM-OP-04",
        )
        self.assertEqual(
            derive_phase({**initial, "official_success": True}), "ARM-VER-01"
        )

    def test_heavy_runtime_dependencies_are_late_imported(self):
        rollout_source = Path(
            "demo/seer_demo/fastwam/rollout.py"
        ).read_text(encoding="utf-8")
        before_runner = rollout_source.split("def run_remote_rollout", 1)[0]
        for dependency in ("import torch", "import numpy", "from lerobot", "from libero"):
            self.assertNotIn(dependency, before_runner)


if __name__ == "__main__":
    unittest.main()
