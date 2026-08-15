import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from seer_demo import presentation as presentation_module
from seer_demo.contracts import load_events
from seer_demo.presentation import (
    build_ffmpeg_command,
    decision_snapshot,
    frame_time_s,
    presentation_event_times,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "demo" / "evidence"


def scenario_events(name: str):
    return load_events(EVIDENCE / f"isaac-{name}-20260815-v2-r4" / "events.jsonl")


class DecisionSnapshotTests(unittest.TestCase):
    def test_cerebellum_snapshot_projects_observed_vehicle_yaw(self):
        events = list(scenario_events("normal"))
        event = events[3]
        events[3] = replace(event, state={**event.state, "yaw_deg": 8.0})

        snapshot = decision_snapshot(events, events[3].sim_time_s)

        self.assertEqual(snapshot["cerebellum"]["yaw_deg"], 8.0)

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

    def test_snapshot_projects_formal_collision_certification(self):
        snapshot = decision_snapshot(
            scenario_events("normal"),
            26.0,
            collision_summary={
                "collision_guard": "2.5D_OBB_SAT_SWEEP_V2",
                "collision_check_semantics": "z-overlapping SAT candidate pairs after explicit allowed-contact filtering",
                "collision_certified": True,
                "forbidden_collision_count": 0,
                "minimum_body_clearance_m": 0.15,
                "collision_check_count": 100,
                "maximum_allowed_contact_error_m": 0.01,
                "maximum_contact_error_m": 0.005,
                "maximum_allowed_horizontal_placement_error_m": 0.02,
                "maximum_horizontal_placement_error_m": 0.01,
                "contact_violation_count": 0,
            },
        )

        self.assertEqual(snapshot["safety"]["collision_guard"], "2.5D_OBB_SAT_SWEEP_V2")
        self.assertTrue(snapshot["safety"]["collision_certified"])
        self.assertEqual(snapshot["safety"]["forbidden_collision_count"], 0)
        self.assertEqual(snapshot["safety"]["minimum_body_clearance_m"], 0.15)

    def test_snapshot_rejects_self_declared_but_incoherent_collision_summary(self):
        with self.assertRaisesRegex(ValueError, "collision certification"):
            decision_snapshot(
                scenario_events("normal"),
                26.0,
                collision_summary={
                    "collision_guard": "WRONG",
                    "collision_certified": True,
                    "forbidden_collision_count": 4,
                },
            )

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
    def test_renderer_fails_closed_without_a_cjk_font(self):
        select_font = getattr(presentation_module, "_select_cjk_font", None)
        self.assertIsNotNone(
            select_font,
            "presentation rendering must select a CJK font explicitly",
        )
        with patch.object(presentation_module, "_font_candidates", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "CJK"):
                select_font()

        self.assertFalse(
            any("DejaVu" in str(path) for path in presentation_module._font_candidates())
        )

    def test_split_builder_binds_summary_to_events_and_source_video(self):
        source = (ROOT / "scripts" / "build_split_presentation.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("assert_summary_matches_validation(summary, validation)", source)
        self.assertIn("assert_video_matches_summary(summary, source_probe)", source)

    def test_frame_time_maps_frame_index_to_source_clock(self):
        self.assertEqual(frame_time_s(0, 8.0), 0.0)
        self.assertEqual(frame_time_s(80, 8.0), 10.0)
        with self.assertRaisesRegex(ValueError, "frame"):
            frame_time_s(-1, 8.0)
        with self.assertRaisesRegex(ValueError, "fps"):
            frame_time_s(1, 0.0)

    def test_presentation_clock_projects_observed_frames_like_the_video(self):
        events = list(scenario_events("normal"))
        times = presentation_event_times(events, 8.0)

        self.assertEqual(times[0], 0.0)
        self.assertEqual(times[-1], 66.0)
        self.assertEqual(times, sorted(times))
        for event, event_time in zip(events, times):
            frame = event.evidence.get("observed_frame")
            if isinstance(frame, int):
                self.assertAlmostEqual(event_time, frame / 8.0)

    def test_presentation_clock_keeps_unobserved_starts_at_previous_boundary(self):
        events = list(scenario_events("recovery"))
        times = presentation_event_times(events, 8.0)

        self.assertEqual(times[0], 0.0)
        self.assertEqual(times[1], 0.0)
        fallback_started_index = next(
            index for index, event in enumerate(events)
            if event.event_type == "fallback_started"
        )
        self.assertEqual(
            times[fallback_started_index],
            times[fallback_started_index - 1],
        )
        self.assertEqual(times[-1], 77.0)

    def test_ffmpeg_command_preserves_clock_and_emits_2560_by_1080(self):
        command = build_ffmpeg_command(
            ffmpeg="/usr/bin/ffmpeg",
            source_video=Path("source.mp4"),
            overlay_pattern=Path("frames/frame-%06d.png"),
            fps=8.0,
            output_video=Path("presentation.mp4"),
        )

        rendered = " ".join(command)
        overlay_arg = next(arg for arg in command if "frame-%06d" in arg)
        self.assertIn("source.mp4", command)
        self.assertEqual(Path(overlay_arg), Path("frames/frame-%06d.png"))
        self.assertIn("presentation.mp4", command)
        self.assertIn("2560:1080", rendered)
        self.assertIn("8", command)
        self.assertIn("yuv420p", command)


if __name__ == "__main__":
    unittest.main()
