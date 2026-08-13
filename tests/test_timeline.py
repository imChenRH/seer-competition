import unittest

from seer_demo.isaac.runner import IsaacTimelineBackend
from seer_demo.isaac.scene import derive_kinematic_observation
from seer_demo.isaac.timeline import FORKLIFT_PARTS, build_timeline


class IsaacTimelineTests(unittest.TestCase):
    def test_scene_parts_use_local_coordinates_and_z_as_height(self):
        for name, part in FORKLIFT_PARTS.items():
            x, y, z = part.local_position
            self.assertLess(abs(x), 3.0, name)
            self.assertLess(abs(y), 2.0, name)
            self.assertGreaterEqual(z, 0.0, name)
        self.assertGreater(FORKLIFT_PARTS["mast_left"].local_position[2], 1.0)
        self.assertEqual(FORKLIFT_PARTS["mast_left"].local_position[1], 0.42)

    def test_normal_timeline_is_monotonic_and_places_payload(self):
        timeline = build_timeline("normal", fps=4)

        self.assertEqual(timeline.duration_s, 51.0)
        self.assertEqual(len(timeline.frames), 51 * 4 + 1)
        self.assertEqual([frame.frame for frame in timeline.frames], list(range(len(timeline.frames))))
        self.assertEqual(
            [frame.sim_time_s for frame in timeline.frames],
            sorted(frame.sim_time_s for frame in timeline.frames),
        )
        attached = [frame for frame in timeline.frames if frame.payload_attached]
        self.assertTrue(attached)
        for frame in attached:
            self.assertAlmostEqual(frame.payload_x_m, frame.base_x_m + 1.6, places=6)
            self.assertAlmostEqual(frame.payload_y_m, frame.base_y_m, places=6)
            self.assertGreater(frame.payload_z_m, frame.mast_height_m)
        final = timeline.frames[-1]
        self.assertFalse(final.payload_attached)
        self.assertTrue(final.payload_placed)
        self.assertEqual(final.outcome, "COMPLETED")
        self.assertAlmostEqual(final.payload_x_m, -3.4)
        self.assertAlmostEqual(final.payload_y_m, -2.0)

    def test_recovery_timeline_contains_visible_fb_f01_lateral_correction(self):
        timeline = build_timeline("recovery", fps=4)

        recovery_frames = [frame for frame in timeline.frames if frame.fallback_id == "FB-F01"]

        self.assertTrue(recovery_frames)
        self.assertAlmostEqual(recovery_frames[0].base_y_m, 0.0, places=2)
        self.assertAlmostEqual(recovery_frames[-1].base_y_m, 0.25, places=2)
        self.assertAlmostEqual(recovery_frames[-1].pallet_lateral_error_m, 0.0, places=6)
        self.assertEqual(timeline.frames[-1].outcome, "COMPLETED")

    def test_intervention_retreats_then_remains_stopped_without_payload(self):
        timeline = build_timeline("intervention", fps=4)

        final = timeline.frames[-1]
        self.assertEqual(final.outcome, "HUMAN_REQUIRED")
        self.assertTrue(final.obstacle_visible)
        self.assertTrue(final.stopped)
        self.assertFalse(any(frame.payload_attached for frame in timeline.frames))
        self.assertAlmostEqual(final.base_x_m, -1.0)
        tail = timeline.frames[-4:]
        self.assertEqual({(frame.base_x_m, frame.base_y_m) for frame in tail}, {(-1.0, 0.0)})

    def test_invalid_fps_and_scenario_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "fps"):
            build_timeline("normal", fps=0)
        with self.assertRaisesRegex(ValueError, "unknown scenario"):
            build_timeline("invented", fps=4)

    def test_skill_result_is_derived_from_observed_stage_state(self):
        timeline = build_timeline("normal", fps=2)
        backend = IsaacTimelineBackend(
            timeline,
            {
                ("skill", "FORK-OP-01", 1): {
                    "payload_attached": False,
                    "_frame": 12,
                }
            },
        )

        result = backend.execute_skill("FORK-OP-01", 1)

        self.assertFalse(result.success)

    def test_fork_tilt_skill_requires_observed_tilt_angle(self):
        timeline = build_timeline("normal", fps=2)
        backend = IsaacTimelineBackend(
            timeline,
            {
                ("skill", "FORK-OP-03", 1): {
                    "fork_tilt_deg": 0.0,
                    "payload_attached": True,
                    "_frame": 20,
                }
            },
        )

        result = backend.execute_skill("FORK-OP-03", 1)

        self.assertFalse(result.success)

    def test_observed_state_is_derived_from_geometry_and_actual_motion(self):
        state = derive_kinematic_observation(
            base=(2.2, 0.25, 0.0),
            lift=(2.2, 0.25, 1.05),
            payload=(3.8, 0.25, 1.30),
            fork_tilt_deg=4.0,
            obstacle_visible=False,
            base_speed_mps=0.0,
        )

        self.assertTrue(state["payload_attached"])
        self.assertFalse(state["payload_placed"])
        self.assertAlmostEqual(state["pallet_lateral_error_m"], 0.0)
        self.assertEqual(state["fork_tilt_deg"], 4.0)
        self.assertTrue(state["stopped"])

        retreat = derive_kinematic_observation(
            base=(-1.0, 0.0, 0.0),
            lift=(-1.0, 0.0, 0.22),
            payload=(3.85, 0.0, 0.32),
            fork_tilt_deg=0.0,
            obstacle_visible=True,
            base_speed_mps=0.2,
        )
        self.assertTrue(retreat["safe_retreat_complete"])
        self.assertFalse(retreat["stopped"])
        self.assertFalse(retreat["payload_attached"])
        self.assertTrue(retreat["obstacle_visible"])


if __name__ == "__main__":
    unittest.main()
