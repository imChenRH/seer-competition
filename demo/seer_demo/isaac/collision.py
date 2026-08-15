"""Pure-Python 2.5D collision checks for deterministic Isaac motion."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
import math

from .layout import (
    INTERVENTION_OBSTACLE_X_OFFSET_M,
    PAYLOAD_ATTACHMENT_X_OFFSET_M,
    PAYLOAD_ATTACHMENT_Z_OFFSET_M,
    active_payload_geometry_specs,
    background_load_geometry_specs,
    container_geometry_specs,
    conveyor_geometry_specs,
    forklift_lift_geometry_specs,
    loading_dock_geometry_specs,
    warehouse_layout_spec,
    warehouse_shell_geometry_specs,
    world_from_local,
)


# Contacts within the rigid lift assembly and between forks and pallet pockets
# are intentional.  Every other pair of independently moving envelopes is
# forbidden and is checked below.
ALLOWED_DYNAMIC_CONTACT_PAIRS = frozenset(
    {
        frozenset(("forklift_body", "fork_carrier")),
        frozenset(("forklift_body", "fork_left")),
        frozenset(("forklift_body", "fork_right")),
        frozenset(("fork_carrier", "fork_left")),
        frozenset(("fork_carrier", "fork_right")),
    }
)
COLLISION_GUARD_VERSION = "2.5D_OBB_SAT_SWEEP_V2"


def _is_allowed_fork_deck_contact(left: OrientedBox, right: OrientedBox) -> bool:
    names = (left.name, right.name)
    if not (
        any(name in {"fork_left", "fork_right"} for name in names)
        and any(name.startswith("active_payload_deck_") for name in names)
    ):
        return False
    fork = left if left.name in {"fork_left", "fork_right"} else right
    deck = right if fork is left else left
    overlap_z = min(fork.z_max, deck.z_max) - max(fork.z_min, deck.z_min)
    # Only a numerically exact support-face contact is allowed.  A fork that
    # penetrates deck thickness by more than 1 mm is a forbidden collision.
    return (
        fork.z_min < deck.z_min
        and fork.z_max <= deck.z_min + 0.001
        and -1e-9 <= overlap_z <= 0.001
    )


def _is_allowed_payload_stack_contact(left: OrientedBox, right: OrientedBox) -> bool:
    names = (left.name, right.name)
    if not (
        any(name.startswith("active_payload_deck_") for name in names)
        and any(name.startswith("active_payload_cargo_") for name in names)
    ):
        return False
    cargo = left if left.name.startswith("active_payload_cargo_") else right
    deck = right if cargo is left else left
    overlap_z = min(cargo.z_max, deck.z_max) - max(cargo.z_min, deck.z_min)
    return (
        cargo.z_max > deck.z_max
        and cargo.z_min >= deck.z_max - 0.001
        and -1e-9 <= overlap_z <= 0.001
    )


def _is_allowed_conveyor_support_contact(
    dynamic: OrientedBox, static: OrientedBox
) -> bool:
    """Allow only the pallet runner's lower face to touch a roller's top face."""
    if not (
        dynamic.name.startswith("active_payload_runner_")
        and static.name.lower().startswith("conveyor_roller")
    ):
        return False
    overlap_z = min(dynamic.z_max, static.z_max) - max(
        dynamic.z_min, static.z_min
    )
    return (
        dynamic.z_max > static.z_max
        and dynamic.z_min >= static.z_max - 0.001
        and -1e-9 <= overlap_z <= 0.001
    )


@dataclass(frozen=True, slots=True)
class Pose2D:
    x_m: float
    y_m: float
    yaw_deg: float

    @property
    def position(self) -> tuple[float, float]:
        return (self.x_m, self.y_m)


@dataclass(frozen=True, slots=True)
class OrientedBox:
    name: str
    center: tuple[float, float]
    size: tuple[float, float]
    yaw_deg: float
    z_min: float
    z_max: float

    def __post_init__(self) -> None:
        values = (*self.center, *self.size, self.yaw_deg, self.z_min, self.z_max)
        if not self.name or not all(math.isfinite(float(value)) for value in values):
            raise ValueError("oriented box values must be finite and named")
        if self.size[0] <= 0.0 or self.size[1] <= 0.0 or self.z_max <= self.z_min:
            raise ValueError("oriented box dimensions must be positive")


@dataclass(frozen=True, slots=True)
class CollisionHit:
    dynamic_name: str
    static_name: str
    sample_index: int
    pose: Pose2D
    frame_index: int | None = None
    phase: str | None = None


@dataclass(frozen=True, slots=True)
class CollisionCertification:
    """Auditable result of checking every swept timeline transition."""

    collision_check_count: int
    minimum_body_clearance_m: float
    maximum_contact_error_m: float
    maximum_horizontal_placement_error_m: float
    forbidden_collision_count: int
    collisions: tuple[CollisionHit, ...]
    contact_violations: tuple[str, ...]

    def to_summary(self) -> dict[str, object]:
        return {
            "collision_guard": COLLISION_GUARD_VERSION,
            "collision_check_count": self.collision_check_count,
            "collision_check_semantics": (
                "z-overlapping SAT candidate pairs after explicit allowed-contact filtering"
            ),
            "minimum_body_clearance_m": self.minimum_body_clearance_m,
            "maximum_allowed_contact_error_m": 0.01,
            "maximum_contact_error_m": self.maximum_contact_error_m,
            "maximum_allowed_horizontal_placement_error_m": 0.02,
            "maximum_horizontal_placement_error_m": (
                self.maximum_horizontal_placement_error_m
            ),
            "forbidden_collision_count": self.forbidden_collision_count,
            "contact_violation_count": len(self.contact_violations),
            "collision_certified": (
                self.forbidden_collision_count == 0
                and not self.contact_violations
                and self.maximum_contact_error_m <= 0.01
                and self.maximum_horizontal_placement_error_m <= 0.02
            ),
        }


def _axes(yaw_deg: float) -> tuple[tuple[float, float], tuple[float, float]]:
    radians = math.radians(yaw_deg)
    cosine, sine = math.cos(radians), math.sin(radians)
    return ((cosine, sine), (-sine, cosine))


def _projection_radius(
    box: OrientedBox,
    axis: tuple[float, float],
    margin_xy: float,
) -> float:
    first, second = _axes(box.yaw_deg)
    half_x = box.size[0] / 2.0 + margin_xy
    half_y = box.size[1] / 2.0 + margin_xy
    return (
        abs(first[0] * axis[0] + first[1] * axis[1]) * half_x
        + abs(second[0] * axis[0] + second[1] * axis[1]) * half_y
    )


def boxes_overlap_3d(
    left: OrientedBox,
    right: OrientedBox,
    *,
    margin_xy: float = 0.0,
) -> bool:
    """Return whether two oriented XY boxes overlap in a shared Z interval."""
    if not math.isfinite(float(margin_xy)) or margin_xy < 0.0:
        raise ValueError("margin_xy must be finite and non-negative")
    if left.z_max < right.z_min or right.z_max < left.z_min:
        return False
    delta = (right.center[0] - left.center[0], right.center[1] - left.center[1])
    for axis in _axes(left.yaw_deg) + _axes(right.yaw_deg):
        center_distance = abs(delta[0] * axis[0] + delta[1] * axis[1])
        limit = _projection_radius(left, axis, margin_xy) + _projection_radius(
            right, axis, 0.0
        )
        if center_distance > limit:
            return False
    return True


def box_separation_xy(left: OrientedBox, right: OrientedBox) -> float:
    """Return a conservative separating-axis clearance in the XY plane."""
    delta = (right.center[0] - left.center[0], right.center[1] - left.center[1])
    gaps = []
    for axis in _axes(left.yaw_deg) + _axes(right.yaw_deg):
        center_distance = abs(delta[0] * axis[0] + delta[1] * axis[1])
        gaps.append(
            center_distance
            - _projection_radius(left, axis, 0.0)
            - _projection_radius(right, axis, 0.0)
        )
    return max(0.0, max(gaps))


def swept_poses(
    start: Pose2D,
    end: Pose2D,
    *,
    translation_step_m: float = 0.025,
    yaw_step_deg: float = 0.5,
) -> tuple[Pose2D, ...]:
    """Sample one pose transition at bounded translation and shortest-yaw steps."""
    if translation_step_m <= 0.0 or yaw_step_deg <= 0.0:
        raise ValueError("swept pose steps must be positive")
    delta_x = end.x_m - start.x_m
    delta_y = end.y_m - start.y_m
    delta_yaw = (end.yaw_deg - start.yaw_deg + 180.0) % 360.0 - 180.0
    count = max(
        1,
        math.ceil(math.hypot(delta_x, delta_y) / translation_step_m),
        math.ceil(abs(delta_yaw) / yaw_step_deg),
    )
    return tuple(
        Pose2D(
            start.x_m + delta_x * index / count,
            start.y_m + delta_y * index / count,
            start.yaw_deg + delta_yaw * index / count,
        )
        for index in range(count + 1)
    )


def find_forbidden_collisions(
    start: Pose2D,
    end: Pose2D,
    static_boxes: tuple[OrientedBox, ...],
    *,
    body_size: tuple[float, float] = (2.2, 1.5),
    body_z: tuple[float, float] = (0.18, 2.50),
    clearance_m: float = 0.05,
) -> tuple[CollisionHit, ...]:
    """Return deterministic body/static collisions across one swept transition."""
    hits: list[CollisionHit] = []
    for sample_index, pose in enumerate(swept_poses(start, end)):
        body = OrientedBox(
            "forklift_body",
            pose.position,
            body_size,
            pose.yaw_deg,
            body_z[0],
            body_z[1],
        )
        for static in static_boxes:
            if boxes_overlap_3d(body, static, margin_xy=clearance_m):
                hits.append(
                    CollisionHit(
                        dynamic_name=body.name,
                        static_name=static.name,
                        sample_index=sample_index,
                        pose=pose,
                    )
                )
    return tuple(hits)


def _world_box(
    name: str,
    *,
    origin: tuple[float, float, float],
    yaw_deg: float,
    local_center: tuple[float, float, float],
    size: tuple[float, float, float],
) -> OrientedBox:
    center = world_from_local(origin, yaw_deg, local_center)
    return OrientedBox(
        name,
        center[:2],
        size[:2],
        yaw_deg,
        center[2] - size[2] / 2.0,
        center[2] + size[2] / 2.0,
    )


def _snake_name(value: str) -> str:
    characters: list[str] = []
    for character in value:
        if characters and (
            character.isupper()
            or (character.isdigit() and not characters[-1].isdigit())
        ):
            characters.append("_")
        characters.append(character.lower())
    return "".join(characters)


@lru_cache(maxsize=3)
def warehouse_static_boxes(scenario: str) -> tuple[OrientedBox, ...]:
    """Mirror the scene's collision-bearing geometry needed by the route guard."""
    if scenario not in {"normal", "recovery", "intervention"}:
        raise ValueError(f"unknown scenario: {scenario}")
    layout = warehouse_layout_spec()
    boxes: list[OrientedBox] = []
    for spec in warehouse_shell_geometry_specs():
        boxes.append(
            _world_box(
                f"warehouse_{_snake_name(spec.name)}",
                origin=(0.0, 0.0, 0.0),
                yaw_deg=0.0,
                local_center=spec.position,
                size=spec.size,
            )
        )
    for spec in loading_dock_geometry_specs():
        boxes.append(
            _world_box(
                f"loading_dock_{_snake_name(spec.name)}",
                origin=layout.loading_dock.position,
                yaw_deg=layout.loading_dock.yaw_deg,
                local_center=spec.position,
                size=spec.size,
            )
        )
    for spec in container_geometry_specs():
        boxes.append(
            _world_box(
                f"container_{_snake_name(spec.name)}",
                origin=layout.container.position,
                yaw_deg=layout.container.yaw_deg,
                local_center=spec.position,
                size=spec.size,
            )
        )
    boxes.append(
        OrientedBox(
            "conveyor_keepout",
            layout.conveyor.position[:2],
            (3.4, 1.5),
            layout.conveyor.yaw_deg,
            0.0,
            0.78,
        )
    )
    for spec in conveyor_geometry_specs():
        boxes.append(
            _world_box(
                f"conveyor_{spec.name}",
                origin=layout.conveyor.position,
                yaw_deg=layout.conveyor.yaw_deg,
                local_center=spec.position,
                size=spec.size,
            )
        )
    for rack_y in (-7.2, 7.2):
        for rack_x in (-12.0, -6.0, 0.0, 6.0, 12.0):
            boxes.append(
                OrientedBox(
                    f"rack_{rack_x:g}_{rack_y:g}",
                    (rack_x, rack_y),
                    (3.9, 1.16),
                    0.0,
                    0.0,
                    4.8,
                )
            )
    for spec in background_load_geometry_specs():
        boxes.append(
            _world_box(
                f"background_{_snake_name(spec.name)}",
                origin=layout.container.position,
                yaw_deg=layout.container.yaw_deg,
                local_center=spec.position,
                size=spec.size,
            )
        )
    if scenario == "intervention":
        obstacle_x = (
            layout.container_payload_target[0] + INTERVENTION_OBSTACLE_X_OFFSET_M
        )
        obstacle_y = layout.container_payload_target[1]
        boxes.extend(
            (
                OrientedBox(
                    "fallen_box_a",
                    (obstacle_x, obstacle_y),
                    (0.85, 0.70),
                    0.0,
                    0.0,
                    0.86,
                ),
                OrientedBox(
                    "fallen_box_b",
                    (obstacle_x + 0.35, obstacle_y + 0.30),
                    (0.65, 0.65),
                    0.0,
                    0.0,
                    0.65,
                ),
            )
        )
    return tuple(boxes)


def _dynamic_boxes(previous, current, pose: Pose2D, amount: float) -> tuple[OrientedBox, ...]:
    mast_height = previous.mast_height_m + (
        current.mast_height_m - previous.mast_height_m
    ) * amount
    fork_tilt_deg = previous.fork_tilt_deg + (
        current.fork_tilt_deg - previous.fork_tilt_deg
    ) * amount
    boxes = [
        OrientedBox(
            "forklift_body",
            pose.position,
            (2.2, 1.5),
            pose.yaw_deg,
            0.18,
            2.50,
        )
    ]
    pitch = math.radians(fork_tilt_deg)
    cosine, sine = math.cos(pitch), math.sin(pitch)
    for spec in forklift_lift_geometry_specs():
        local_x, local_y, local_z = spec.position
        pitched_x = local_x * cosine + local_z * sine
        pitched_z = -local_x * sine + local_z * cosine
        projected_size_x = abs(spec.size[0] * cosine) + abs(spec.size[2] * sine)
        projected_half_z = (
            abs(spec.size[0] * sine) + abs(spec.size[2] * cosine)
        ) / 2.0
        center = world_from_local(
            (pose.x_m, pose.y_m, 0.0),
            pose.yaw_deg,
            (pitched_x, local_y, mast_height + pitched_z),
        )
        name = {
            "Carrier": "fork_carrier",
            "ForkLeft": "fork_left",
            "ForkRight": "fork_right",
        }[spec.name]
        boxes.append(
            OrientedBox(
                name,
                center[:2],
                (projected_size_x, spec.size[1]),
                pose.yaw_deg,
                center[2] - projected_half_z,
                center[2] + projected_half_z,
            )
        )
    payload_x = previous.payload_x_m + (
        current.payload_x_m - previous.payload_x_m
    ) * amount
    payload_y = previous.payload_y_m + (
        current.payload_y_m - previous.payload_y_m
    ) * amount
    payload_z = previous.payload_z_m + (
        current.payload_z_m - previous.payload_z_m
    ) * amount
    payload_delta_yaw = (
        current.payload_yaw_deg - previous.payload_yaw_deg + 180.0
    ) % 360.0 - 180.0
    payload_yaw = previous.payload_yaw_deg + payload_delta_yaw * amount
    for index, spec in enumerate(active_payload_geometry_specs()):
        center = world_from_local(
            (payload_x, payload_y, payload_z),
            payload_yaw,
            spec.position,
        )
        boxes.append(
            OrientedBox(
                f"active_payload_{spec.role}_{index}",
                center[:2],
                spec.size[:2],
                payload_yaw,
                center[2] - spec.size[2] / 2.0,
                center[2] + spec.size[2] / 2.0,
            )
        )
    return tuple(boxes)


def _transition_sample_count(previous, current) -> int:
    base_count = len(
        swept_poses(
            Pose2D(previous.base_x_m, previous.base_y_m, previous.yaw_deg),
            Pose2D(current.base_x_m, current.base_y_m, current.yaw_deg),
        )
    ) - 1
    payload_distance = math.sqrt(
        (current.payload_x_m - previous.payload_x_m) ** 2
        + (current.payload_y_m - previous.payload_y_m) ** 2
        + (current.payload_z_m - previous.payload_z_m) ** 2
    )
    payload_delta_yaw = (
        current.payload_yaw_deg - previous.payload_yaw_deg + 180.0
    ) % 360.0 - 180.0
    return max(
        1,
        base_count,
        math.ceil(payload_distance / 0.025),
        math.ceil(abs(payload_delta_yaw) / 0.5),
        math.ceil(abs(current.mast_height_m - previous.mast_height_m) / 0.025),
        math.ceil(abs(current.fork_tilt_deg - previous.fork_tilt_deg) / 0.5),
    )


def _transition_samples(previous, current) -> tuple[tuple[Pose2D, float], ...]:
    count = _transition_sample_count(previous, current)
    delta_yaw = (current.yaw_deg - previous.yaw_deg + 180.0) % 360.0 - 180.0
    return tuple(
        (
            Pose2D(
                previous.base_x_m
                + (current.base_x_m - previous.base_x_m) * index / count,
                previous.base_y_m
                + (current.base_y_m - previous.base_y_m) * index / count,
                previous.yaw_deg + delta_yaw * index / count,
            ),
            index / count,
        )
        for index in range(count + 1)
    )


def dynamic_boxes_for_transition(previous, current) -> tuple[tuple[OrientedBox, ...], ...]:
    """Expose sampled, rendered-equivalent dynamic envelopes for tests/audit."""
    return tuple(
        _dynamic_boxes(previous, current, pose, amount)
        for pose, amount in _transition_samples(previous, current)
    )


def _scan_transition(previous, current, scenario: str):
    statics = warehouse_static_boxes(scenario)
    samples = _transition_samples(previous, current)
    hits: list[CollisionHit] = []
    minimum_body_clearance = math.inf
    check_count = 0
    for sample_index, (pose, amount) in enumerate(samples):
        dynamic_boxes = _dynamic_boxes(previous, current, pose, amount)
        for dynamic in dynamic_boxes:
            for static in statics:
                is_exact_conveyor_part = static.name.startswith("conveyor_") and (
                    static.name != "conveyor_keepout"
                )
                if dynamic.name == "forklift_body" and is_exact_conveyor_part:
                    continue
                if dynamic.name != "forklift_body" and static.name == "conveyor_keepout":
                    continue
                if dynamic.z_max < static.z_min or static.z_max < dynamic.z_min:
                    continue
                check_count += 1
                if dynamic.name == "forklift_body":
                    minimum_body_clearance = min(
                        minimum_body_clearance,
                        box_separation_xy(dynamic, static),
                    )
                margin = 0.05 if dynamic.name == "forklift_body" else 0.0
                if boxes_overlap_3d(dynamic, static, margin_xy=margin):
                    if _is_allowed_conveyor_support_contact(dynamic, static):
                        continue
                    hits.append(
                        CollisionHit(
                            dynamic_name=dynamic.name,
                            static_name=static.name,
                            sample_index=sample_index,
                            pose=pose,
                            frame_index=current.frame,
                            phase=current.phase,
                        )
                    )
        for left, right in combinations(dynamic_boxes, 2):
            pair = frozenset((left.name, right.name))
            if (
                pair in ALLOWED_DYNAMIC_CONTACT_PAIRS
                or _is_allowed_fork_deck_contact(left, right)
                or _is_allowed_payload_stack_contact(left, right)
            ):
                continue
            if left.z_max < right.z_min or right.z_max < left.z_min:
                continue
            check_count += 1
            if boxes_overlap_3d(left, right):
                hits.append(
                    CollisionHit(
                        dynamic_name=left.name,
                        static_name=right.name,
                        sample_index=sample_index,
                        pose=pose,
                        frame_index=current.frame,
                        phase=current.phase,
                    )
                )
    return tuple(hits), check_count, minimum_body_clearance


def certify_timeline(timeline) -> CollisionCertification:
    """Certify every frame transition, failing closed on any forbidden contact."""
    hits: list[CollisionHit] = []
    minimum_clearance = math.inf
    maximum_contact_error = 0.0
    maximum_horizontal_placement_error = 0.0
    contact_violations: list[str] = []
    check_count = 0
    layout = warehouse_layout_spec()
    for frame in timeline.frames:
        if frame.payload_attached:
            expected_x, expected_y, _ = world_from_local(
                (frame.base_x_m, frame.base_y_m, 0.0),
                frame.yaw_deg,
                (PAYLOAD_ATTACHMENT_X_OFFSET_M, 0.0, 0.0),
            )
            attachment_error = math.sqrt(
                (frame.payload_x_m - expected_x) ** 2
                + (frame.payload_y_m - expected_y) ** 2
                + (
                    frame.payload_z_m
                    - frame.mast_height_m
                    - PAYLOAD_ATTACHMENT_Z_OFFSET_M
                )
                ** 2
            )
            maximum_contact_error = max(maximum_contact_error, attachment_error)
            if attachment_error > 0.01:
                contact_violations.append(
                    f"frame {frame.frame} attachment position error "
                    f"{attachment_error:.6f}"
                )
            yaw_error = abs(
                (frame.payload_yaw_deg - frame.yaw_deg + 180.0) % 360.0 - 180.0
            )
            if yaw_error > 0.5:
                contact_violations.append(
                    f"frame {frame.frame} attached payload yaw error {yaw_error:.6f}"
                )
            continue
        expected_z = (
            layout.conveyor_payload_target[2]
            if frame.payload_placed
            else layout.container_payload_target[2]
        )
        contact_error = abs(frame.payload_z_m - expected_z)
        maximum_contact_error = max(maximum_contact_error, contact_error)
        if contact_error > 0.01:
            contact_violations.append(
                f"frame {frame.frame} payload support error {contact_error:.6f}"
            )
        if frame.payload_placed:
            placement_error = math.hypot(
                frame.payload_x_m - layout.conveyor_payload_target[0],
                frame.payload_y_m - layout.conveyor_payload_target[1],
            )
            maximum_horizontal_placement_error = max(
                maximum_horizontal_placement_error, placement_error
            )
            if placement_error > 0.02:
                contact_violations.append(
                    f"frame {frame.frame} placement position error "
                    f"{placement_error:.6f}"
                )
    for previous, current in zip(timeline.frames, timeline.frames[1:]):
        transition_hits, transition_checks, transition_clearance = _scan_transition(
            previous, current, timeline.scenario
        )
        hits.extend(transition_hits)
        check_count += transition_checks
        minimum_clearance = min(minimum_clearance, transition_clearance)
        if not previous.payload_placed and current.payload_placed:
            delta_time = current.sim_time_s - previous.sim_time_s
            speed = (
                math.hypot(
                    current.base_x_m - previous.base_x_m,
                    current.base_y_m - previous.base_y_m,
                )
                / delta_time
                if delta_time > 0.0
                else math.inf
            )
            if speed > 0.02:
                contact_violations.append(
                    f"frame {current.frame} release speed {speed:.6f}"
                )
            if abs(current.fork_tilt_deg) > 0.01:
                contact_violations.append(
                    f"frame {current.frame} release tilt {current.fork_tilt_deg:.6f}"
                )
    if math.isinf(minimum_clearance):
        minimum_clearance = 0.0
    return CollisionCertification(
        collision_check_count=check_count,
        minimum_body_clearance_m=round(minimum_clearance, 6),
        maximum_contact_error_m=round(maximum_contact_error, 6),
        maximum_horizontal_placement_error_m=round(
            maximum_horizontal_placement_error, 6
        ),
        forbidden_collision_count=len(hits),
        collisions=tuple(hits),
        contact_violations=tuple(contact_violations),
    )


def assert_timeline_collision_safe(timeline) -> CollisionCertification:
    certification = certify_timeline(timeline)
    if certification.collisions or certification.contact_violations:
        if not certification.collisions:
            raise RuntimeError(
                "forbidden contact condition: " + certification.contact_violations[0]
            )
        first = certification.collisions[0]
        raise RuntimeError(
            "forbidden swept collision: "
            f"{first.dynamic_name} vs {first.static_name} at "
            f"frame {first.frame_index} phase {first.phase} "
            f"({first.pose.x_m:.3f}, {first.pose.y_m:.3f}, {first.pose.yaw_deg:.2f})"
        )
    return certification


def assert_frame_transition_safe(previous, current, scenario: str) -> None:
    """Re-check the imminent kinematic transform before authoring it to USD."""
    hits, _, _ = _scan_transition(previous, current, scenario)
    if hits:
        first = hits[0]
        raise RuntimeError(
            "forbidden frame transition: "
            f"{first.dynamic_name} vs {first.static_name} before frame {current.frame}"
        )
