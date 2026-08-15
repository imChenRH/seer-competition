import unittest
import math
from dataclasses import replace

from seer_demo.isaac import runner as isaac_runner
from seer_demo.isaac import scene as isaac_scene
from seer_demo.isaac.runner import IsaacTimelineBackend, annotate_payload_settle_state
from seer_demo.isaac.collision import (
    OrientedBox,
    Pose2D,
    box_separation_xy,
    boxes_overlap_3d,
    assert_timeline_collision_safe,
    certify_timeline,
    dynamic_boxes_for_transition,
    find_forbidden_collisions,
    swept_poses,
    warehouse_static_boxes,
)
from seer_demo.isaac.layout import (
    CONVEYOR_SUPPORT_TOP_M,
    PAYLOAD_ATTACHMENT_X_OFFSET_M,
    active_payload_geometry_specs,
    container_geometry_specs,
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
    payload_dynamic_for_frame,
    warehouse_asset_specs,
    warehouse_rack_positions,
)
from seer_demo.isaac.timeline import FORKLIFT_PARTS, build_timeline
from seer_demo.scenarios import skill_state_succeeded


class IsaacTimelineTests(unittest.TestCase):
    def test_payload_pose_matches_vehicle_and_facility_yaw(self):
        timeline = build_timeline("normal", fps=8)
        attached = next(frame for frame in timeline.frames if frame.payload_attached)
        placed = timeline.frames[-1]
        initial = timeline.frames[0]

        self.assertEqual(initial.payload_yaw_deg, warehouse_layout_spec().container.yaw_deg)
        self.assertEqual(attached.payload_yaw_deg, attached.yaw_deg)
        self.assertEqual(placed.payload_yaw_deg, warehouse_layout_spec().conveyor.yaw_deg)

    def test_tilted_fork_and_carrier_envelopes_follow_shared_transform(self):
        timeline = build_timeline("normal", fps=8)
        tilted = next(
            frame for frame in reversed(timeline.frames)
            if frame.phase == "tilt_stabilize"
        )
        boxes = {
            box.name: box
            for box in dynamic_boxes_for_transition(tilted, tilted)[0]
        }

        self.assertGreater(boxes["fork_left"].z_max - boxes["fork_left"].z_min, 0.10)
        self.assertIn("fork_carrier", boxes)

    def test_forks_contact_deck_without_intersecting_cargo(self):
        specs = active_payload_geometry_specs()
        deck_top = max(
            spec.position[2] + spec.size[2] / 2
            for spec in specs
            if spec.role == "deck"
        )
        cargo_bottom = min(
            spec.position[2] - spec.size[2] / 2
            for spec in specs
            if spec.role == "cargo"
        )
        self.assertAlmostEqual(cargo_bottom, deck_top)

        timeline = build_timeline("normal", fps=8)
        attached_index = next(
            index for index, frame in enumerate(timeline.frames)
            if frame.payload_attached
        )
        boxes = dynamic_boxes_for_transition(
            timeline.frames[attached_index], timeline.frames[attached_index]
        )[0]
        forks = [box for box in boxes if box.name in {"fork_left", "fork_right"}]
        cargos = [
            box for box in boxes if box.name.startswith("active_payload_cargo_")
        ]
        decks = [
            box for box in boxes if box.name.startswith("active_payload_deck_")
        ]

        self.assertFalse(
            any(boxes_overlap_3d(fork, cargo) for fork in forks for cargo in cargos)
        )
        self.assertTrue(
            any(
                box_separation_xy(fork, deck) == 0.0
                and abs(fork.z_max - deck.z_min) <= 1e-6
                for fork in forks
                for deck in decks
            )
        )

    def test_payload_clearance_and_dynamic_pair_guard_reject_carrier_overlap(self):
        timeline = build_timeline("normal", fps=8)
        attached_index = next(
            index for index, frame in enumerate(timeline.frames)
            if frame.payload_attached
        )
        attached = timeline.frames[attached_index]
        forged_x, forged_y, _ = world_from_local(
            (attached.base_x_m, attached.base_y_m, 0.0),
            attached.yaw_deg,
            (1.60, 0.0, 0.0),
        )
        forged_frames = list(timeline.frames)
        forged_frames[attached_index] = replace(
            attached,
            payload_x_m=forged_x,
            payload_y_m=forged_y,
        )
        forged = replace(timeline, frames=tuple(forged_frames))

        certification = certify_timeline(forged)

        self.assertTrue(
            any(
                "fork_carrier" in {hit.dynamic_name, hit.static_name}
                and any(
                    name.startswith("active_payload_")
                    for name in {hit.dynamic_name, hit.static_name}
                )
                for hit in certification.collisions
            ),
            certification.collisions[:8],
        )

    def test_static_guard_contains_every_collision_shell_and_container_rail(self):
        names = {box.name for box in warehouse_static_boxes("normal")}

        self.assertTrue(
            {
                "warehouse_back_wall",
                "warehouse_side_wall",
                "warehouse_ceiling_beam_0",
                "container_right_top_rail",
                "container_roof_back_rail",
            }.issubset(names)
        )

    def test_collision_certification_rejects_a_forged_colliding_timeline(self):
        timeline = build_timeline("normal", fps=8)
        collision_index = next(
            index for index, frame in enumerate(timeline.frames)
            if frame.phase == "route_conveyor"
        )
        forged_frames = list(timeline.frames)
        forged_frames[collision_index] = replace(
            forged_frames[collision_index],
            base_x_m=-6.0,
            base_y_m=-4.2,
            yaw_deg=-6.0,
        )
        forged = replace(timeline, frames=tuple(forged_frames))

        with self.assertRaisesRegex(RuntimeError, "forbidden swept collision"):
            assert_timeline_collision_safe(forged)

    def test_collision_certification_includes_forks_not_only_chassis(self):
        timeline = build_timeline("normal", fps=8)
        collision_index = next(
            index for index, frame in enumerate(timeline.frames)
            if frame.phase == "align_conveyor"
        )
        layout = warehouse_layout_spec()
        forged_position = world_from_local(
            layout.conveyor.position,
            layout.conveyor.yaw_deg,
            (-3.3, 0.66, 0.0),
        )
        forged_frames = list(timeline.frames)
        forged_frames[collision_index] = replace(
            forged_frames[collision_index],
            base_x_m=forged_position[0],
            base_y_m=forged_position[1],
            yaw_deg=layout.conveyor.yaw_deg,
            mast_height_m=0.11,
        )
        forged = replace(timeline, frames=tuple(forged_frames))

        certification = certify_timeline(forged)

        self.assertTrue(
            any(hit.dynamic_name.startswith("fork_") for hit in certification.collisions),
            certification.collisions[:5],
        )

    def test_collision_certification_exports_formal_summary_fields(self):
        summary = certify_timeline(build_timeline("normal", fps=8)).to_summary()

        self.assertEqual(summary["collision_guard"], "2.5D_OBB_SAT_SWEEP_V2")
        self.assertTrue(summary["collision_certified"])
        self.assertEqual(summary["forbidden_collision_count"], 0)
        self.assertGreater(summary["collision_check_count"], 0)
        self.assertGreaterEqual(summary["minimum_body_clearance_m"], 0.05)
        self.assertEqual(summary["maximum_allowed_contact_error_m"], 0.01)
        self.assertLessEqual(summary["maximum_contact_error_m"], 0.01)
        self.assertEqual(
            summary["maximum_allowed_horizontal_placement_error_m"], 0.02
        )
        self.assertLessEqual(summary["maximum_horizontal_placement_error_m"], 0.02)
        self.assertEqual(summary["contact_violation_count"], 0)

    def test_contact_certification_rejects_forged_support_height(self):
        timeline = build_timeline("normal", fps=8)
        forged_frames = list(timeline.frames)
        forged_frames[-1] = replace(
            forged_frames[-1], payload_z_m=forged_frames[-1].payload_z_m + 0.02
        )

        certification = certify_timeline(
            replace(timeline, frames=tuple(forged_frames))
        )

        self.assertGreater(certification.maximum_contact_error_m, 0.01)
        self.assertTrue(certification.contact_violations)
        self.assertFalse(certification.to_summary()["collision_certified"])

    def test_collision_certification_rejects_payload_below_container_floor(self):
        timeline = build_timeline("normal", fps=8)
        forged_frames = list(timeline.frames)
        forged_frames[0] = replace(
            forged_frames[0], payload_z_m=forged_frames[0].payload_z_m - 0.009
        )

        certification = certify_timeline(
            replace(timeline, frames=tuple(forged_frames))
        )

        self.assertTrue(
            any(
                hit.dynamic_name.startswith("active_payload_runner_")
                and hit.static_name == "container_floor"
                for hit in certification.collisions
            )
        )
        self.assertFalse(certification.to_summary()["collision_certified"])

    def test_contact_certification_rejects_detached_fixed_joint_pose(self):
        timeline = build_timeline("normal", fps=8)
        forged_frames = list(timeline.frames)
        attached_index = next(
            index for index, frame in enumerate(forged_frames)
            if frame.payload_attached
        )
        forged_frames[attached_index] = replace(
            forged_frames[attached_index],
            payload_x_m=forged_frames[attached_index].payload_x_m + 0.10,
        )

        certification = certify_timeline(
            replace(timeline, frames=tuple(forged_frames))
        )

        self.assertTrue(
            any("attachment position error" in item for item in certification.contact_violations)
        )
        self.assertFalse(certification.to_summary()["collision_certified"])

    def test_contact_certification_rejects_horizontal_placement_error(self):
        timeline = build_timeline("normal", fps=8)
        forged_frames = list(timeline.frames)
        forged_frames[-1] = replace(
            forged_frames[-1], payload_x_m=forged_frames[-1].payload_x_m + 0.03
        )

        certification = certify_timeline(
            replace(timeline, frames=tuple(forged_frames))
        )

        self.assertTrue(
            any("placement position error" in item for item in certification.contact_violations)
        )
        self.assertFalse(certification.to_summary()["collision_certified"])

    def test_transition_sampling_covers_payload_yaw_when_base_is_stationary(self):
        timeline = build_timeline("normal", fps=8)
        frame = timeline.frames[0]
        rotated = replace(frame, payload_yaw_deg=frame.payload_yaw_deg + 90.0)

        samples = dynamic_boxes_for_transition(frame, rotated)

        self.assertGreaterEqual(len(samples), 181)

    def test_all_scenarios_have_zero_forbidden_swept_collisions(self):
        for scenario in ("normal", "recovery", "intervention"):
            certification = certify_timeline(build_timeline(scenario, fps=8))

            self.assertEqual(
                certification.forbidden_collision_count,
                0,
                (scenario, certification.collisions[:3]),
            )
            self.assertGreaterEqual(certification.minimum_body_clearance_m, 0.05)
            self.assertGreater(certification.collision_check_count, 0)

    def test_conveyor_approach_aligns_yaw_before_advancing_straight(self):
        for scenario in ("normal", "recovery"):
            frames = build_timeline(scenario, fps=8).frames
            prealign = [frame for frame in frames if frame.phase == "prealign_conveyor"]
            final_approach = [frame for frame in frames if frame.phase == "align_conveyor"]

            self.assertTrue(prealign)
            self.assertTrue(final_approach)
            expected_yaw = warehouse_layout_spec().conveyor.yaw_deg
            self.assertAlmostEqual(prealign[-1].yaw_deg, expected_yaw, places=6)
            self.assertEqual({frame.yaw_deg for frame in final_approach}, {expected_yaw})

    def test_payload_support_heights_are_derived_without_penetration(self):
        layout = warehouse_layout_spec()

        self.assertAlmostEqual(layout.container_payload_target[2], 0.125, places=6)
        self.assertAlmostEqual(layout.conveyor_payload_target[2], 0.780, places=6)

    def test_attachment_does_not_teleport_payload_vertically(self):
        frames = build_timeline("normal", fps=8).frames
        attached_index = next(
            index for index, frame in enumerate(frames) if frame.payload_attached
        )
        before = frames[attached_index - 1]
        after = frames[attached_index]

        self.assertFalse(before.payload_attached)
        self.assertLessEqual(abs(after.payload_z_m - before.payload_z_m), 0.02)

    def test_conveyor_uses_cross_width_cylindrical_support_rollers(self):
        rollers = [
            spec
            for spec in conveyor_geometry_specs()
            if spec.role == "support_roller"
        ]

        self.assertGreaterEqual(len(rollers), 9)
        for roller in rollers:
            self.assertEqual(getattr(roller, "primitive", None), "cylinder")
            self.assertEqual(getattr(roller, "axis", None), "y")
            self.assertGreaterEqual(roller.size[1], 1.10)
            self.assertAlmostEqual(
                roller.position[2] + roller.size[2] / 2.0,
                CONVEYOR_SUPPORT_TOP_M,
                places=6,
            )

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
        touching = OrientedBox("touching", (0.0, 0.0), (1.0, 1.0), 0.0, 0.5, 1.0)

        self.assertFalse(boxes_overlap_3d(low, high))
        self.assertFalse(boxes_overlap_3d(left, right))
        self.assertTrue(boxes_overlap_3d(low, rotated_overlap))
        self.assertTrue(boxes_overlap_3d(low, touching))

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

    def test_container_and_conveyor_follow_the_ground_lane_heading(self):
        layout = warehouse_layout_spec()

        self.assertEqual(layout.container.yaw_deg, 0.0)
        self.assertEqual(layout.conveyor.yaw_deg, 0.0)
        self.assertEqual(layout.container.yaw_deg, layout.loading_dock.yaw_deg)
        separation = math.dist(layout.container.position[:2], layout.conveyor.position[:2])
        self.assertGreater(separation, 8.0)
        self.assertGreater(abs(layout.container.position[1] - layout.conveyor.position[1]), 4.0)
        self.assertGreaterEqual(layout.conveyor_body_clearance_m, 0.45)

    def test_shipping_container_is_large_relative_to_the_forklift(self):
        specs = container_geometry_specs()
        x_min = min(spec.position[0] - spec.size[0] / 2.0 for spec in specs)
        x_max = max(spec.position[0] + spec.size[0] / 2.0 for spec in specs)
        y_min = min(spec.position[1] - spec.size[1] / 2.0 for spec in specs)
        y_max = max(spec.position[1] + spec.size[1] / 2.0 for spec in specs)
        z_min = min(spec.position[2] - spec.size[2] / 2.0 for spec in specs)
        z_max = max(spec.position[2] + spec.size[2] / 2.0 for spec in specs)

        self.assertGreaterEqual(x_max - x_min, 7.5)
        self.assertGreaterEqual(y_max - y_min, 3.4)
        self.assertGreaterEqual(z_max - z_min, 3.5)

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

    def test_hidden_fault_obstacle_is_not_an_active_collider(self):
        normal = {item.name for item in static_physics_contract("normal")}
        intervention = {
            item.name for item in static_physics_contract("intervention")
        }

        self.assertNotIn("obstacle", normal)
        self.assertIn("obstacle", intervention)

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

    def test_payload_becomes_dynamic_only_after_release(self):
        timeline = build_timeline("normal", fps=8)

        self.assertEqual(
            [payload_dynamic_for_frame(frame) for frame in timeline.frames],
            [frame.payload_placed for frame in timeline.frames],
        )

    def test_placement_has_a_bounded_supported_settle_window(self):
        timeline = build_timeline("normal", fps=8)
        placed = [frame for frame in timeline.frames if frame.payload_placed]

        self.assertGreaterEqual(len(placed), timeline.fps + 1)
        self.assertTrue(all(frame.payload_supported for frame in placed))
        self.assertFalse(placed[0].payload_settled)
        self.assertTrue(placed[-1].payload_settled)
        self.assertEqual(placed[0].outcome, "RUNNING")
        self.assertEqual(placed[-1].outcome, "COMPLETED")

    def test_place_skill_requires_supported_and_settled_payload(self):
        base_state = {
            "payload_attached": False,
            "payload_placed": True,
            "payload_supported": True,
            "payload_settled": True,
        }

        self.assertTrue(skill_state_succeeded("FORK-OP-04", base_state))
        self.assertFalse(
            skill_state_succeeded(
                "FORK-OP-04", {**base_state, "payload_supported": False}
            )
        )
        self.assertFalse(
            skill_state_succeeded(
                "FORK-OP-04", {**base_state, "payload_settled": False}
            )
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
        self.assertTrue(all(spec.path.suffix in {".usd", ".usda"} for spec in specs))
        self.assertTrue(all(spec.path.parts[1:3] == ("assets", "warehouse") for spec in specs))
        self.assertTrue(all(spec.path.parts[-3:-1] == ("materials", "physics") for spec in specs))

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

    def test_subject_aware_camera_keeps_the_complete_forklift_in_every_frame(self):
        build_poses = getattr(isaac_scene, "camera_poses_for_timeline", None)
        frame_margin = getattr(isaac_scene, "camera_frame_margin", None)
        self.assertIsNotNone(build_poses)
        self.assertIsNotNone(frame_margin)

        for scenario in ("normal", "recovery", "intervention"):
            timeline = build_timeline(scenario, fps=8)
            poses = build_poses(timeline)
            self.assertEqual(len(poses), len(timeline.frames))
            margins = [
                frame_margin(frame, pose, aspect_ratio=16.0 / 9.0)
                for frame, pose in zip(timeline.frames, poses)
            ]

            self.assertGreaterEqual(min(margins), 0.05, scenario)
            self.assertLess(
                max(
                    math.dist(previous.position, current.position)
                    for previous, current in zip(poses, poses[1:])
                ),
                2.0,
                scenario,
            )

    def test_scene_parts_use_local_coordinates_and_z_as_height(self):
        for name, part in FORKLIFT_PARTS.items():
            x, y, z = part.local_position
            self.assertLess(abs(x), 3.0, name)
            self.assertLess(abs(y), 2.0, name)
            self.assertGreaterEqual(z, 0.0, name)
        self.assertGreater(FORKLIFT_PARTS["mast_left"].local_position[2], 1.0)
        self.assertEqual(FORKLIFT_PARTS["mast_left"].local_position[1], 0.42)

    def test_all_four_wheels_touch_the_ground_plane(self):
        for name in ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"):
            wheel = FORKLIFT_PARTS[name]
            wheel_bottom = wheel.local_position[2] - wheel.size[2] / 2.0

            self.assertAlmostEqual(wheel_bottom, 0.0, places=6, msg=name)

    def test_all_four_wheels_are_cylinders_on_the_lateral_axis(self):
        for name in ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"):
            wheel = FORKLIFT_PARTS[name]

            self.assertEqual(getattr(wheel, "primitive", None), "cylinder", name)
            self.assertEqual(getattr(wheel, "axis", None), "y", name)

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
                (PAYLOAD_ATTACHMENT_X_OFFSET_M, 0.0, frame.payload_z_m),
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

    def test_timeline_keeps_vehicle_aligned_with_parallel_facilities(self):
        timeline = build_timeline("normal", fps=4)

        layout = warehouse_layout_spec()
        container_aligned = [frame for frame in timeline.frames if frame.phase == "precision_approach"][-1]
        conveyor_aligned = [frame for frame in timeline.frames if frame.phase == "align_conveyor"][-1]
        self.assertAlmostEqual(container_aligned.yaw_deg, layout.container.yaw_deg)
        self.assertAlmostEqual(conveyor_aligned.yaw_deg, layout.conveyor.yaw_deg)
        self.assertGreater(
            abs(container_aligned.base_y_m - conveyor_aligned.base_y_m),
            4.0,
        )

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

    def test_isaac_backend_durations_follow_timeline_frame_clock(self):
        timeline = build_timeline("normal", fps=8)
        backend = IsaacTimelineBackend(
            timeline,
            {
                ("skill", "FORK-NAV-01", 1): {
                    "base_x_m": 1.0,
                    "_frame": 80,
                },
                ("skill", "FORK-NAV-03", 1): {
                    "base_x_m": 2.0,
                    "_frame": 144,
                },
            },
        )

        first = backend.execute_skill("FORK-NAV-01", 1)
        second = backend.execute_skill("FORK-NAV-03", 1)

        self.assertEqual(first.duration_s, 10.0)
        self.assertEqual(second.duration_s, 8.0)

    def test_later_internal_route_cannot_overwrite_first_business_skill_observation(self):
        capture = getattr(isaac_runner, "capture_action_observation", None)
        self.assertIsNotNone(capture, "runner must expose the action-observation contract")
        observations = {}
        key = ("skill", "FORK-NAV-01", 1)
        capture(
            observations,
            key,
            {"base_x_m": 4.3, "_frame": 80},
        )
        capture(
            observations,
            key,
            {"base_x_m": -10.7, "_frame": 384},
        )
        backend = IsaacTimelineBackend(build_timeline("normal", fps=2), observations)

        result = backend.execute_skill("FORK-NAV-01", 1)

        self.assertTrue(result.success)
        self.assertEqual(result.evidence["observed_frame"], 80)
        self.assertEqual(result.state["base_x_m"], 4.3)

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
        payload_x, payload_y, _ = world_from_local(
            (2.2, 0.25, 0.0),
            30.0,
            (PAYLOAD_ATTACHMENT_X_OFFSET_M, 0.0, 0.0),
        )
        state = derive_kinematic_observation(
            base=(2.2, 0.25, 0.0),
            lift=(2.2, 0.25, 1.05),
            payload=(payload_x, payload_y, 1.065),
            yaw_deg=30.0,
            payload_yaw_deg=30.0,
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

    def test_conveyor_support_is_derived_from_measured_payload_pose(self):
        layout = warehouse_layout_spec()
        target = layout.conveyor_payload_target
        supported = derive_kinematic_observation(
            base=(-3.25, -4.2, 0.0),
            lift=(-3.25, -4.2, 0.765),
            payload=target,
            yaw_deg=layout.conveyor.yaw_deg,
            fork_tilt_deg=0.0,
            obstacle_visible=False,
            base_speed_mps=0.0,
            physical_attachment_enabled=False,
            payload_yaw_deg=layout.conveyor.yaw_deg,
        )
        floating = derive_kinematic_observation(
            base=(-3.25, -4.2, 0.0),
            lift=(-3.25, -4.2, 0.765),
            payload=(target[0], target[1], target[2] + 0.02),
            yaw_deg=layout.conveyor.yaw_deg,
            fork_tilt_deg=0.0,
            obstacle_visible=False,
            base_speed_mps=0.0,
            physical_attachment_enabled=False,
            payload_yaw_deg=layout.conveyor.yaw_deg,
        )

        self.assertTrue(supported["payload_supported"])
        self.assertEqual(supported["payload_support_error_m"], 0.0)
        self.assertFalse(floating["payload_supported"])

    def test_settle_state_requires_measured_support_and_low_payload_speed(self):
        stationary = {
            "payload_x_m": -7.05,
            "payload_y_m": -4.2,
            "payload_z_m": 0.78,
            "payload_supported": True,
        }
        moving = dict(stationary)
        moving["payload_x_m"] = -7.04

        annotate_payload_settle_state(stationary, (-7.05, -4.2, 0.78), 0.125)
        annotate_payload_settle_state(moving, (-7.05, -4.2, 0.78), 0.125)

        self.assertTrue(stationary["payload_settled"])
        self.assertEqual(stationary["payload_speed_mps"], 0.0)
        self.assertFalse(moving["payload_settled"])
        self.assertGreater(moving["payload_speed_mps"], 0.02)

    def test_precision_alignment_uses_measured_local_target_error_not_world_x(self):
        aligned = {
            "base_x_m": 1.341728,
            "precision_alignment_error_m": 0.0,
        }
        outside_tolerance = {
            "base_x_m": 2.0,
            "precision_alignment_error_m": 0.011,
        }

        self.assertTrue(skill_state_succeeded("FORK-NAV-03", aligned))
        self.assertFalse(skill_state_succeeded("FORK-NAV-03", outside_tolerance))

    def test_intervention_navigation_uses_its_scenario_specific_safe_target(self):
        annotate = getattr(isaac_runner, "annotate_navigation_target_error", None)
        self.assertIsNotNone(
            annotate,
            "runner must compare observed navigation poses with each timeline target",
        )
        timeline = build_timeline("intervention", fps=2)
        cases = (
            (
                "FORK-NAV-01",
                next(
                    frame
                    for frame in reversed(timeline.frames)
                    if frame.phase == "enter_container"
                ),
            ),
            (
                "FORK-NAV-03",
                next(
                    frame
                    for frame in reversed(timeline.frames)
                    if frame.phase == "precision_approach"
                ),
            ),
        )

        for skill_id, target_frame in cases:
            with self.subTest(skill_id=skill_id):
                observed = target_frame.to_observed_state()
                annotate(observed, target_frame)
                self.assertAlmostEqual(observed["navigation_target_error_m"], 0.0)
                self.assertTrue(skill_state_succeeded(skill_id, observed))

                outside_tolerance = dict(observed)
                outside_tolerance["navigation_target_error_m"] = 0.011
                self.assertFalse(skill_state_succeeded(skill_id, outside_tolerance))

    def test_observation_reports_precision_alignment_error_in_container_frame(self):
        layout = warehouse_layout_spec()
        target = world_from_local(
            layout.container.position,
            layout.container.yaw_deg,
            layout.container_alignment_local,
        )
        state = derive_kinematic_observation(
            base=target,
            lift=(target[0], target[1], 0.11),
            payload=layout.container_payload_target,
            yaw_deg=layout.container.yaw_deg,
            payload_yaw_deg=layout.container.yaw_deg,
            fork_tilt_deg=0.0,
            obstacle_visible=False,
            base_speed_mps=0.0,
            physical_attachment_enabled=False,
        )

        self.assertAlmostEqual(state.get("precision_alignment_error_m", -1.0), 0.0)

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
