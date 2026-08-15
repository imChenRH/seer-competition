import unittest
import math

from seer_demo.isaac.runner import IsaacTimelineBackend
from seer_demo.isaac.collision import (
    OrientedBox,
    Pose2D,
    boxes_overlap_3d,
    find_forbidden_collisions,
    swept_poses,
)
from seer_demo.isaac.layout import (
    conveyor_geometry_specs,
    local_from_world,
    static_physics_contract,
    warehouse_layout_spec,
    world_from_local,
)
from seer_demo.isaac.scene import (
    FORK_POCKET_CENTERS_Y,
    PHYSICS_SCHEMA_APIS,
    WAREHOUSE_EXTENT_M,
    camera_pose_for_phase,
    derive_kinematic_observation,
    pallet_part_specs,
    physical_attachment_for_frame,
    warehouse_asset_specs,
    warehouse_rack_positions,
)
from seer_demo.isaac.timeline import FORKLIFT_PARTS, build_timeline


class IsaacTimelineTests(unittest.TestCase):
    def test_payload_support_heights_are_derived_without_penetration(self):
        layout = warehouse_layout_spec()

        self.assertAlmostEqual(layout.container_payload_target[2], 0.125, places=6)
        self.assertAlmostEqual(layout.conveyor_payload_target[2], 0.785, places=6)

    def test_attachment_does_not_teleport_payload_vertically(self):
        frames = build_timeline("normal", fps=8).frames
        attached_index = next(
            index for index, frame in enumerate(frames) if frame.payload_attached
        )
        before = frames[attached_index - 1]
        after = frames[attached_index]

        self.assertFalse(before.payload_attached)
        self.assertLessEqual(abs(after.payload_z_m - before.payload_z_m), 0.02)

    def test_conveyor_support_lanes_leave_both_fork_channels_open(self):
        support_lanes = {
            (
                round(spec.position[1] - spec.size[1] / 2.0, 6),
                round(spec.position[1] + spec.size[1] / 2.0, 6),
            )
            for spec in conveyor_geometry_specs()
            if spec.role == "support_roller"
        }
        fork_channels = ((-0.385, -0.255), (0.255, 0.385))

        self.assertEqual(len(support_lanes), 3)
        for lane_min, lane_max in support_lanes:
            for channel_min, channel_max in fork_channels:
                self.assertTrue(lane_max <= channel_min or channel_max <= lane_min)

    def test_swept_guard_detects_the_old_diagonal_conveyor_clip(self):
        start = Pose2D(-0.985402, 1.191240, 8.0)
        end = Pose2D(-9.281922, -3.855056, -6.0)
        conveyor = OrientedBox(
            "conveyor_keepout",
            (-6.0, -4.2),
            (3.2, 1.35),
            -6.0,
            0.0,
            0.78,
        )

        collisions = find_forbidden_collisions(start, end, (conveyor,))

        self.assertTrue(collisions)
        self.assertEqual(collisions[0].dynamic_name, "forklift_body")
        self.assertEqual(collisions[0].static_name, "conveyor_keepout")
        self.assertGreaterEqual(collisions[0].sample_index, 1)

    def test_obb_guard_respects_xy_and_z_separation(self):
        low = OrientedBox("low", (0.0, 0.0), (1.0, 1.0), 0.0, 0.0, 0.5)
        high = OrientedBox("high", (0.0, 0.0), (1.0, 1.0), 0.0, 0.6, 1.0)
        left = OrientedBox("left", (-2.0, 0.0), (1.0, 1.0), 25.0, 0.0, 1.0)
        right = OrientedBox("right", (2.0, 0.0), (1.0, 1.0), -25.0, 0.0, 1.0)
        rotated_overlap = OrientedBox(
            "rotated_overlap", (0.5, 0.0), (1.0, 1.0), 45.0, 0.0, 1.0
        )

        self.assertFalse(boxes_overlap_3d(low, high))
        self.assertFalse(boxes_overlap_3d(left, right))
        self.assertTrue(boxes_overlap_3d(low, rotated_overlap))

    def test_swept_pose_sampling_respects_translation_and_yaw_limits(self):
        poses = swept_poses(
            Pose2D(0.0, 0.0, 179.0),
            Pose2D(0.10, 0.0, -179.0),
            translation_step_m=0.025,
            yaw_step_deg=0.5,
        )

        self.assertEqual(len(poses), 5)
        self.assertEqual(poses[0], Pose2D(0.0, 0.0, 179.0))
        self.assertAlmostEqual(poses[-1].x_m, 0.10)
        self.assertAlmostEqual(poses[-1].yaw_deg, 181.0)
        for previous, current in zip(poses, poses[1:]):
            self.assertLessEqual(math.dist(previous.position, current.position), 0.0250001)
            self.assertLessEqual(abs(current.yaw_deg - previous.yaw_deg), 0.500001)

    def test_rotated_facilities_are_separated_and_not_facing_each_other(self):
        layout = warehouse_layout_spec()

        self.assertEqual(layout.container.yaw_deg, 8.0)
        self.assertEqual(layout.conveyor.yaw_deg, -6.0)
        self.assertNotEqual(layout.container.yaw_deg, layout.loading_dock.yaw_deg)
        separation = math.dist(layout.container.position[:2], layout.conveyor.position[:2])
        self.assertGreater(separation, 8.0)
        self.assertGreater(abs(layout.container.position[1] - layout.conveyor.position[1]), 4.0)
        self.assertGreaterEqual(layout.conveyor_body_clearance_m, 0.45)

    def test_all_key_facilities_have_an_explicit_static_collision_role(self):
        contract = {item.name: item for item in static_physics_contract()}

        self.assertEqual(
            set(contract),
            {
                "ground",
                "warehouse_shell",
                "racks",
                "container",
                "loading_dock",
                "conveyor",
                "background_loads",
                "obstacle",
            },
        )
        self.assertTrue(all(item.collision_enabled for item in contract.values()))
        self.assertTrue(all(item.rigid_body_kind == "static" for item in contract.values()))

    def test_scene_physics_contract_includes_required_usd_apis(self):
        self.assertEqual(
            set(PHYSICS_SCHEMA_APIS),
            {
                "PhysicsScene",
                "CollisionAPI",
                "RigidBodyAPI",
                "MassAPI",
                "ArticulationRootAPI",
                "FixedJoint",
            },
        )

    def test_pallet_has_two_open_fork_pockets_aligned_with_forks(self):
        parts = pallet_part_specs()

        self.assertEqual(FORK_POCKET_CENTERS_Y, (-0.32, 0.32))
        self.assertGreaterEqual(len(parts), 5)
        runners = [part for part in parts if part.role == "runner"]
        for pocket_y in FORK_POCKET_CENTERS_Y:
            self.assertTrue(
                all(abs(part.position[1] - pocket_y) > (part.size[1] + 0.16) / 2 for part in runners)
            )

    def test_explicit_physics_attachment_tracks_payload_coupling_only(self):
        timeline = build_timeline("normal", fps=2)

        self.assertEqual(
            [physical_attachment_for_frame(frame) for frame in timeline.frames],
            [frame.payload_attached for frame in timeline.frames],
        )

    def test_large_warehouse_layout_keeps_central_task_lane_clear(self):
        self.assertGreaterEqual(WAREHOUSE_EXTENT_M[0], 40.0)
        self.assertGreaterEqual(WAREHOUSE_EXTENT_M[1], 26.0)
        racks = warehouse_rack_positions()
        self.assertGreaterEqual(len(racks), 8)
        self.assertTrue(all(abs(y) >= 4.5 for _, y in racks))
        self.assertTrue(all(abs(x) <= WAREHOUSE_EXTENT_M[0] / 2 for x, _ in racks))

    def test_simready_asset_specs_use_official_physics_material_library(self):
        specs = warehouse_asset_specs("/assets/warehouse")

        self.assertGreaterEqual(len(specs), 4)
        self.assertTrue(all("/Props/materials/physics/" in str(spec.path) for spec in specs))
        self.assertTrue(all(spec.path.suffix in {".usd", ".usda"} for spec in specs))
        self.assertTrue(all(str(spec.path).startswith("/assets/warehouse/") for spec in specs))

    def test_camera_strategy_uses_distinct_internal_operation_views(self):
        establishing = camera_pose_for_phase("enter_container")
        pickup = camera_pose_for_phase("insert_forks")
        placement = camera_pose_for_phase("place_payload")

        self.assertNotEqual(establishing.position, pickup.position)
        self.assertNotEqual(pickup.position, placement.position)
        self.assertLess(pickup.position[1], 0.0)
        self.assertLess(abs(placement.position[1]), 3.3)
        self.assertAlmostEqual(pickup.look_at[0], 3.1, places=1)
        self.assertAlmostEqual(placement.look_at[0], -6.8, places=1)

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

        self.assertGreaterEqual(timeline.duration_s, 55.0)
        self.assertEqual(len(timeline.frames), int(timeline.duration_s * 4) + 1)
        self.assertEqual([frame.frame for frame in timeline.frames], list(range(len(timeline.frames))))
        self.assertEqual(
            [frame.sim_time_s for frame in timeline.frames],
            sorted(frame.sim_time_s for frame in timeline.frames),
        )
        attached = [frame for frame in timeline.frames if frame.payload_attached]
        self.assertTrue(attached)
        for frame in attached:
            expected_x, expected_y, _ = world_from_local(
                (frame.base_x_m, frame.base_y_m, 0.0),
                frame.yaw_deg,
                (1.6, 0.0, frame.payload_z_m),
            )
            self.assertAlmostEqual(frame.payload_x_m, expected_x, places=5)
            self.assertAlmostEqual(frame.payload_y_m, expected_y, places=5)
            self.assertGreater(frame.payload_z_m, frame.mast_height_m)
        final = timeline.frames[-1]
        self.assertFalse(final.payload_attached)
        self.assertTrue(final.payload_placed)
        self.assertEqual(final.outcome, "COMPLETED")
        layout = warehouse_layout_spec()
        self.assertAlmostEqual(final.payload_x_m, layout.conveyor_payload_target[0], places=6)
        self.assertAlmostEqual(final.payload_y_m, layout.conveyor_payload_target[1], places=6)

    def test_timeline_visibly_turns_both_directions_and_aligns_to_facilities(self):
        timeline = build_timeline("normal", fps=4)

        yaw_values = [frame.yaw_deg for frame in timeline.frames]
        self.assertGreater(max(yaw_values), 7.5)
        self.assertLess(min(yaw_values), -5.5)
        container_aligned = [frame for frame in timeline.frames if frame.phase == "precision_approach"][-1]
        conveyor_aligned = [frame for frame in timeline.frames if frame.phase == "align_conveyor"][-1]
        self.assertAlmostEqual(container_aligned.yaw_deg, 8.0)
        self.assertAlmostEqual(conveyor_aligned.yaw_deg, -6.0)

    def test_recovery_timeline_contains_visible_fb_f01_lateral_correction(self):
        timeline = build_timeline("recovery", fps=4)

        recovery_frames = [frame for frame in timeline.frames if frame.fallback_id == "FB-F01"]

        self.assertTrue(recovery_frames)
        layout = warehouse_layout_spec()
        first_local = local_from_world(
            layout.container.position,
            layout.container.yaw_deg,
            (recovery_frames[0].base_x_m, recovery_frames[0].base_y_m, 0.0),
        )
        last_local = local_from_world(
            layout.container.position,
            layout.container.yaw_deg,
            (recovery_frames[-1].base_x_m, recovery_frames[-1].base_y_m, 0.0),
        )
        self.assertAlmostEqual(first_local[1], 0.0, places=2)
        self.assertAlmostEqual(last_local[1], 0.25, places=2)
        self.assertAlmostEqual(recovery_frames[-1].pallet_lateral_error_m, 0.0, places=6)
        self.assertEqual(timeline.frames[-1].outcome, "COMPLETED")

    def test_intervention_retreats_then_remains_stopped_without_payload(self):
        timeline = build_timeline("intervention", fps=4)

        final = timeline.frames[-1]
        self.assertEqual(final.outcome, "HUMAN_REQUIRED")
        self.assertTrue(final.obstacle_visible)
        self.assertTrue(final.stopped)
        self.assertFalse(any(frame.payload_attached for frame in timeline.frames))
        layout = warehouse_layout_spec()
        exit_target = world_from_local(
            layout.container.position,
            layout.container.yaw_deg,
            layout.container_exit_local,
        )
        self.assertAlmostEqual(final.base_x_m, exit_target[0], places=6)
        self.assertAlmostEqual(final.base_y_m, exit_target[1], places=6)
        tail = timeline.frames[-4:]
        self.assertEqual(
            {(frame.base_x_m, frame.base_y_m) for frame in tail},
            {(round(exit_target[0], 6), round(exit_target[1], 6))},
        )

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
            payload=(3.585641, 1.05, 1.065),
            yaw_deg=30.0,
            fork_tilt_deg=4.0,
            obstacle_visible=False,
            base_speed_mps=0.0,
            physical_attachment_enabled=True,
        )

        self.assertTrue(state["payload_attached"])
        self.assertFalse(state["payload_placed"])
        self.assertAlmostEqual(state["pallet_lateral_error_m"], 0.0)
        self.assertEqual(state["fork_tilt_deg"], 4.0)
        self.assertEqual(state["yaw_deg"], 30.0)
        self.assertTrue(state["stopped"])

        retreat = derive_kinematic_observation(
            base=(-1.0, 0.0, 0.0),
            lift=(-1.0, 0.0, 0.22),
            payload=(3.85, 0.0, 0.32),
            yaw_deg=0.0,
            fork_tilt_deg=0.0,
            obstacle_visible=True,
            base_speed_mps=0.2,
            physical_attachment_enabled=False,
        )
        self.assertTrue(retreat["safe_retreat_complete"])
        self.assertFalse(retreat["stopped"])
        self.assertFalse(retreat["payload_attached"])
        self.assertTrue(retreat["obstacle_visible"])

    def test_geometry_alignment_without_fixed_joint_is_not_reported_as_attached(self):
        state = derive_kinematic_observation(
            base=(2.2, 0.0, 0.0),
            lift=(2.2, 0.0, 1.05),
            payload=(3.8, 0.0, 1.30),
            yaw_deg=0.0,
            fork_tilt_deg=4.0,
            obstacle_visible=False,
            base_speed_mps=0.0,
            physical_attachment_enabled=False,
        )

        self.assertFalse(state["payload_attached"])
        self.assertFalse(state["physical_attachment_enabled"])

    def test_unattached_pallet_error_is_measured_in_vehicle_local_coordinates(self):
        layout = warehouse_layout_spec()
        base = world_from_local(
            layout.container.position,
            layout.container.yaw_deg,
            layout.container_alignment_local,
        )
        payload = layout.container_payload_target

        state = derive_kinematic_observation(
            base=base,
            lift=(base[0], base[1], 0.22),
            payload=payload,
            yaw_deg=layout.container.yaw_deg,
            fork_tilt_deg=0.0,
            obstacle_visible=False,
            base_speed_mps=0.0,
            physical_attachment_enabled=False,
        )

        self.assertAlmostEqual(state["pallet_lateral_error_m"], 0.0, places=6)

    def test_view_adjustment_reports_container_local_lateral_offset(self):
        layout = warehouse_layout_spec()
        base = world_from_local(
            layout.container.position,
            layout.container.yaw_deg,
            (2.2, -0.15, 0.0),
        )

        state = derive_kinematic_observation(
            base=base,
            lift=(base[0], base[1], 0.22),
            payload=layout.container_payload_target,
            yaw_deg=layout.container.yaw_deg,
            fork_tilt_deg=0.0,
            obstacle_visible=True,
            base_speed_mps=0.0,
            physical_attachment_enabled=False,
        )

        self.assertAlmostEqual(state["camera_lateral_offset_m"], -0.15, places=6)


if __name__ == "__main__":
    unittest.main()
