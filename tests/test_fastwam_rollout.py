import math
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from seer_demo.fastwam.rollout import (
    CANONICAL_POLICY_PROMPT,
    _encode_attempt_video,
    batch_single_robot_state,
    derive_phase,
    load_policy_on_cuda,
    validate_policy_action,
)
from seer_demo.fastwam.preflight import validate_preflight_record
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
        for model in (apple, plate):
            self.assertIsNotNone(model.find("./worldbody/body/body[@name='object']"))
            for site_name in ("bottom_site", "top_site", "horizontal_radius_site"):
                self.assertIsNotNone(
                    model.find(f"./worldbody/body/site[@name='{site_name}']")
                )
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

    def test_remote_launcher_pins_the_resolved_official_libero_runtime(self):
        launcher = Path("scripts/run_fastwam_demo.sh").read_text(encoding="utf-8")

        self.assertIn('mujoco.__version__ == "3.8.1"', launcher)
        self.assertNotIn('mujoco.__version__ == "3.3.2"', launcher)

    def test_recording_frames_are_removed_after_each_attempt_is_encoded(self):
        rollout_source = Path("demo/seer_demo/fastwam/rollout.py").read_text(
            encoding="utf-8"
        )
        encoded = rollout_source.index("_encode_video(frames_dir")
        removed = rollout_source.index("shutil.rmtree(frames_dir)", encoded)

        self.assertGreater(removed, encoded)

    def test_empty_attempt_does_not_invoke_ffmpeg_and_mask_root_error(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            frames.mkdir()

            self.assertFalse(_encode_attempt_video(frames, root / "simulation.mp4", 20))
            self.assertFalse((root / "simulation.mp4").exists())

    def test_preflight_record_binds_official_task_cameras_and_one_action(self):
        record = {
            "schema_version": "1.0",
            "task_suite": "libero_goal",
            "task_id": 8,
            "task_name": "put_the_bowl_on_the_plate",
            "task_description": "put the bowl on the plate",
            "policy_prompt": "Put the bowl on the plate",
            "observation_shapes": {
                "image": [224, 224, 3],
                "image2": [224, 224, 3],
            },
            "action": [0.0] * 7,
            "versions": {
                "lerobot": "0.6.2",
                "mujoco": "3.8.1",
                "torch": "2.11.0+cu128",
            },
            "cuda_device": "NVIDIA GeForce RTX 4090",
            "elapsed_s": 1.25,
        }

        validated = validate_preflight_record(record)

        self.assertEqual(validated, record)
        self.assertNotIn("model_dir", json.dumps(validated))

    def test_preflight_rejects_wrong_task_or_malformed_action(self):
        base = {
            "schema_version": "1.0",
            "task_suite": "libero_goal",
            "task_id": 8,
            "task_name": "put_the_bowl_on_the_plate",
            "task_description": "put the bowl on the plate",
            "policy_prompt": "Put the bowl on the plate",
            "observation_shapes": {
                "image": [224, 224, 3],
                "image2": [224, 224, 3],
            },
            "action": [0.0] * 7,
            "versions": {"lerobot": "0.6.2", "mujoco": "3.8.1", "torch": "2.11"},
            "cuda_device": "RTX 4090",
            "elapsed_s": 1.0,
        }
        for update in ({"task_id": 7}, {"action": [0.0] * 6}):
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    validate_preflight_record({**base, **update})

    def test_preflight_keeps_gpu_dependencies_late_imported(self):
        source = Path("demo/seer_demo/fastwam/preflight.py").read_text(
            encoding="utf-8"
        )
        before_runner = source.split("def run_preflight", 1)[0]
        for dependency in ("import torch", "import mujoco", "from lerobot", "from libero"):
            self.assertNotIn(dependency, before_runner)

    def test_policy_loads_weights_on_cpu_before_one_cuda_move(self):
        calls = []

        class FakeConfig:
            device = "unset"
            n_action_steps = 32

            @classmethod
            def from_pretrained(cls, model_dir):
                calls.append(("config", model_dir))
                return cls()

        class FakeModel:
            device = "cpu"

        class FakePolicy:
            model = FakeModel()

            @classmethod
            def from_pretrained(cls, model_dir, *, config):
                calls.append(("load", model_dir, config.device))
                return cls()

            def to(self, device):
                calls.append(("move", device))
                return self

        class FakeTorch:
            @staticmethod
            def device(value):
                return f"torch:{value}"

        config, policy = load_policy_on_cuda(
            Path("/model"), FakeConfig, FakePolicy, FakeTorch
        )

        self.assertEqual(
            calls,
            [("config", "/model"), ("load", "/model", "cpu"), ("move", "cuda")],
        )
        self.assertEqual(config.device, "cuda")
        self.assertEqual(config.n_action_steps, 10)
        self.assertEqual(policy.model.device, "torch:cuda")

    def test_single_environment_robot_state_is_batched_without_mutating_raw_observation(self):
        class FakeArray:
            def __init__(self, name):
                self.name = name
                self.ndim = 1

            def __getitem__(self, index):
                self.last_index = index
                return ("batched", self.name)

        quat = FakeArray("quat")
        observation = {
            "pixels": {"image": "raw-image"},
            "robot_state": {
                "eef": {"quat": quat},
                "gripper": {"qpos": FakeArray("qpos")},
            },
        }

        batched = batch_single_robot_state(observation)

        self.assertEqual(batched["robot_state"]["eef"]["quat"], ("batched", "quat"))
        self.assertEqual(
            batched["robot_state"]["gripper"]["qpos"], ("batched", "qpos")
        )
        self.assertIs(observation["robot_state"]["eef"]["quat"], quat)
        self.assertEqual(batched["pixels"], observation["pixels"])

    def test_rollout_uses_reference_precomputed_context_without_resident_text_encoder(self):
        rollout_source = Path("demo/seer_demo/fastwam/rollout.py").read_text(
            encoding="utf-8"
        )
        preflight_source = Path("demo/seer_demo/fastwam/preflight.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def precompute_task_context", rollout_source)
        self.assertIn("config.prompt_template.format(task=task)", rollout_source)
        self.assertIn("context = context.clone()", rollout_source)
        self.assertIn("context[~context_mask] = 0.0", rollout_source)
        self.assertIn("torch_module.ones_like(context_mask", rollout_source)
        self.assertIn('policy_observation["context"] = task_context', rollout_source)
        self.assertIn('policy_observation["context_mask"] = task_context_mask', rollout_source)
        self.assertNotIn('policy_observation["task"]', rollout_source)
        self.assertIn('policy_observation["context"] = task_context', preflight_source)
        self.assertNotIn('policy_observation["task"]', preflight_source)


if __name__ == "__main__":
    unittest.main()
