import tempfile
import unittest
from pathlib import Path

from seer_demo.contracts import EventWriter, load_events
from seer_demo.fastwam.contracts import ActionRecord, FASTWAM_SCENARIO, FASTWAM_SKILLS
from seer_demo.fastwam.presentation import (
    FASTWAM_PRESENTATION_SIZE,
    action_at_frame,
    fastwam_snapshot,
    fastwam_theme,
)


class FastWamPresentationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        path = Path(self.temporary.name) / "events.jsonl"
        with EventWriter(path, "fastwam-present", FASTWAM_SCENARIO, "fastwam_policy") as writer:
            writer.emit(
                "task_started",
                0.0,
                status="RUNNING",
                message="把红色苹果放入黄色盘子",
                evidence={"observed_frame": 0},
            )
            for index, skill_id in enumerate(FASTWAM_SKILLS, 1):
                writer.emit(
                    "skill_started",
                    index / 20,
                    status="RUNNING",
                    skill_id=skill_id,
                    evidence={"observed_frame": index * 5},
                )
                writer.emit(
                    "skill_completed",
                    index / 20,
                    status="RUNNING",
                    skill_id=skill_id,
                    state={
                        "apple_lift_m": 0.04 if index >= 5 else 0.0,
                        "plate_xy_error_m": 0.04 if index >= 7 else 0.3,
                        "gripper_closed": 4 <= index <= 7,
                        "official_success": skill_id == "ARM-VER-01",
                    },
                    evidence={"observed_frame": index * 5},
                )
            writer.emit(
                "task_completed",
                2.1,
                status="COMPLETED",
                state={"official_success": True, "plate_xy_error_m": 0.02},
                evidence={"observed_frame": 42},
            )
        self.events = load_events(path)
        self.actions = [
            ActionRecord(
                "1.0",
                "fastwam-present",
                index,
                index + 1,
                (index + 1) / 20,
                tuple(round((index + axis) / 100, 3) for axis in range(7)),
                index % 10 == 0,
                0.21 if index % 10 == 0 else 0.001,
            )
            for index in range(42)
        ]
        self.summary = {
            "run_id": "fastwam-present",
            "terminal_status": "COMPLETED",
            "official_success": True,
            "selected_attempt": 2,
            "attempts": [
                {"attempt_index": index, "success": index == 2} for index in range(5)
            ],
        }

    def test_action_projection_uses_latest_observed_frame(self):
        self.assertIsNone(action_at_frame(self.actions, 0))
        self.assertEqual(action_at_frame(self.actions, 1), self.actions[0])
        self.assertEqual(action_at_frame(self.actions, 42), self.actions[41])

    def test_snapshot_projects_only_observed_state_and_action(self):
        snapshot = fastwam_snapshot(
            self.events, self.actions, self.summary, frame=42
        )

        self.assertEqual(snapshot.phase, "ARM-VER-01")
        self.assertEqual(snapshot.action, self.actions[41].action)
        self.assertEqual(snapshot.layer, "Fast-WAM policy action")
        self.assertTrue(snapshot.official_success)
        document = snapshot.to_dict()
        self.assertNotIn("reasoning", document)
        self.assertNotIn("thought", document)
        self.assertNotIn("chain_of_thought", document)

    def test_green_theme_requires_observed_official_success(self):
        running = fastwam_snapshot(self.events, self.actions, self.summary, frame=35)
        completed = fastwam_snapshot(self.events, self.actions, self.summary, frame=42)

        self.assertNotEqual(fastwam_theme(running).name, "VERIFIED")
        self.assertEqual(fastwam_theme(completed).name, "VERIFIED")
        forged_summary = {**self.summary, "official_success": True}
        early = fastwam_snapshot(self.events, self.actions, forged_summary, frame=10)
        self.assertFalse(early.official_success)

    def test_presentation_contract_is_2560_by_1080(self):
        self.assertEqual(FASTWAM_PRESENTATION_SIZE, (2560, 1080))
        source = Path("scripts/build_fastwam_presentation.py").read_text(encoding="utf-8")
        self.assertIn("validate_fastwam_package(summary, events, actions)", source)
        self.assertIn("assert_video_matches_summary(summary, source_probe)", source)
        self.assertIn("presentation frame count changed", source)


if __name__ == "__main__":
    unittest.main()
