import unittest
from pathlib import Path

from seer_demo.contracts import load_events
from seer_demo.presentation import (
    build_ffmpeg_command,
    decision_snapshot,
    frame_time_s,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "demo" / "evidence"


def scenario_events(name: str):
    return load_events(EVIDENCE / f"isaac-{name}-20260813" / "events.jsonl")


class DecisionSnapshotTests(unittest.TestCase):
    def test_normal_snapshot_projects_brain_dispatch_and_cerebellum_observation(self):
        snapshot = decision_snapshot(scenario_events("normal"), 26.0)

        self.assertEqual(snapshot["goal"], "卸载3号集装箱货物到A区传送带")
        self.assertEqual(snapshot["current_skill_id"], "FORK-OP-02")
        self.assertEqual(snapshot["brain"]["dispatch"], "举升载荷")
        self.assertEqual(snapshot["brain"]["mode"], "NORMAL")
        self.assertEqual(snapshot["cerebellum"]["controller"], "货叉高度闭环")
        self.assertEqual(snapshot["safety"]["gate"], "CLEAR")
        self.assertEqual(snapshot["audit"]["latest_sequence"], 9)
        self.assertNotIn("chain_of_thought", snapshot)
        self.assertNotIn("thought_process", snapshot)

    def test_recovery_snapshot_shows_failed_perception_and_fallback_dispatch(self):
        snapshot = decision_snapshot(scenario_events("recovery"), 24.0)

        self.assertEqual(snapshot["status"], "FALLBACK")
        self.assertEqual(snapshot["current_skill_id"], "FORK-PER-01")
        self.assertEqual(snapshot["fallback_id"], "FB-F01")
        self.assertEqual(snapshot["brain"]["mode"], "RECOVERY")
        self.assertIn("重新识别", snapshot["brain"]["dispatch"])
        self.assertEqual(snapshot["cerebellum"]["controller"], "横向重对位")
        self.assertEqual(snapshot["safety"]["gate"], "CLEAR")
        self.assertEqual(snapshot["audit"]["latest_sequence"], 7)
        self.assertEqual([item["sequence"] for item in snapshot["audit"]["recent"]], [5, 6, 7])

    def test_intervention_snapshot_prioritizes_safety_gate_and_operator_handoff(self):
        snapshot = decision_snapshot(scenario_events("intervention"), 36.0)

        self.assertEqual(snapshot["status"], "HUMAN_REQUIRED")
        self.assertEqual(snapshot["brain"]["mode"], "HUMAN_HANDOFF")
        self.assertEqual(snapshot["brain"]["dispatch"], "暂停自主任务，等待操作员确认")
        self.assertEqual(snapshot["cerebellum"]["controller"], "安全制动保持")
        self.assertEqual(snapshot["safety"]["gate"], "BLOCKED")
        self.assertTrue(snapshot["safety"]["stopped"])
        self.assertEqual(snapshot["audit"]["latest_sequence"], 17)

    def test_time_before_first_event_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "event"):
            decision_snapshot(scenario_events("normal"), -0.01)


class PresentationMediaTests(unittest.TestCase):
    def test_frame_time_maps_frame_index_to_source_clock(self):
        self.assertEqual(frame_time_s(0, 8.0), 0.0)
        self.assertEqual(frame_time_s(80, 8.0), 10.0)
        with self.assertRaisesRegex(ValueError, "frame"):
            frame_time_s(-1, 8.0)
        with self.assertRaisesRegex(ValueError, "fps"):
            frame_time_s(1, 0.0)

    def test_ffmpeg_command_preserves_clock_and_emits_2560_by_1080(self):
        command = build_ffmpeg_command(
            ffmpeg="/usr/bin/ffmpeg",
            source_video=Path("source.mp4"),
            overlay_pattern=Path("frames/frame-%06d.png"),
            fps=8.0,
            output_video=Path("presentation.mp4"),
        )

        rendered = " ".join(command)
        self.assertIn("source.mp4", command)
        self.assertIn("frames/frame-%06d.png", command)
        self.assertIn("presentation.mp4", command)
        self.assertIn("2560:1080", rendered)
        self.assertIn("8", command)
        self.assertIn("yuv420p", command)


if __name__ == "__main__":
    unittest.main()
