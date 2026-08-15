"""Pure-Python 2.5D collision checks for deterministic Isaac motion."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .layout import warehouse_layout_spec, world_from_local


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


@dataclass(frozen=True, slots=True)
class CollisionCertification:
    """Auditable result of checking every swept timeline transition."""

    collision_check_count: int
    minimum_body_clearance_m: float
    forbidden_collision_count: int
    collisions: tuple[CollisionHit, ...]

    def to_summary(self) -> dict[str, object]:
        return {
            "collision_guard": "2.5D_OBB_SAT_SWEEP_V1",
            "collision_check_count": self.collision_check_count,
            "minimum_body_clearance_m": self.minimum_body_clearance_m,
            "maximum_allowed_contact_error_m": 0.01,
            "forbidden_collision_count": self.forbidden_collision_count,
            "collision_certified": self.forbidden_collision_count == 0,
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
    if left.z_max <= right.z_min or right.z_max <= left.z_min:
        return False
    delta = (right.center[0] - left.center[0], right.center[1] - left.center[1])
    for axis in _axes(left.yaw_deg) + _axes(right.yaw_deg):
        center_distance = abs(delta[0] * axis[0] + delta[1] * axis[1])
        limit = _projection_radius(left, axis, margin_xy) + _projection_radius(
            right, axis, 0.0
        )
        if center_distance >= limit:
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


def warehouse_static_boxes(scenario: str) -> tuple[OrientedBox, ...]:
    """Mirror the scene's collision-bearing geometry needed by the route guard."""
    if scenario not in {"normal", "recovery", "intervention"}:
        raise ValueError(f"unknown scenario: {scenario}")
    layout = warehouse_layout_spec()
    boxes: list[OrientedBox] = [
        _world_box(
            "loading_dock_deck",
            origin=layout.loading_dock.position,
            yaw_deg=layout.loading_dock.yaw_deg,
            local_center=(0.0, 0.0, 0.11),
            size=(6.0, 1.1, 0.22),
        ),
        _world_box(
            "loading_dock_bumper",
            origin=layout.loading_dock.position,
            yaw_deg=layout.loading_dock.yaw_deg,
            local_center=(-3.0, 0.0, 0.26),
            size=(0.30, 1.1, 0.52),
        ),
        _world_box(
            "container_back",
            origin=layout.container.position,
            yaw_deg=layout.container.yaw_deg,
            local_center=(6.0, 0.0, 1.50),
            size=(0.12, 2.8, 3.0),
        ),
        _world_box(
            "container_left",
            origin=layout.container.position,
            yaw_deg=layout.container.yaw_deg,
            local_center=(3.0, 1.40, 1.50),
            size=(6.0, 0.10, 3.0),
        ),
        _world_box(
            "container_door_left",
            origin=layout.container.position,
            yaw_deg=layout.container.yaw_deg,
            local_center=(0.0, -1.22, 1.50),
            size=(0.12, 0.12, 3.0),
        ),
        _world_box(
            "container_door_right",
            origin=layout.container.position,
            yaw_deg=layout.container.yaw_deg,
            local_center=(0.0, 1.22, 1.50),
            size=(0.12, 0.12, 3.0),
        ),
        OrientedBox(
            "conveyor_keepout",
            layout.conveyor.position[:2],
            (3.2, 1.35),
            layout.conveyor.yaw_deg,
            0.0,
            0.78,
        ),
    ]
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
    for index, (local_x, local_y) in enumerate(((4.9, 0.82), (4.9, -0.82))):
        boxes.append(
            _world_box(
                f"background_load_{index}",
                origin=layout.container.position,
                yaw_deg=layout.container.yaw_deg,
                local_center=(local_x, local_y, 0.49),
                size=(1.0, 0.75, 0.98),
            )
        )
    if scenario == "intervention":
        obstacle_x = layout.container_payload_target[0] - 0.70
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


def certify_timeline(timeline) -> CollisionCertification:
    """Certify every frame transition, failing closed on any forbidden contact."""
    statics = warehouse_static_boxes(timeline.scenario)
    hits: list[CollisionHit] = []
    minimum_clearance = math.inf
    check_count = 0
    for previous, current in zip(timeline.frames, timeline.frames[1:]):
        poses = swept_poses(
            Pose2D(previous.base_x_m, previous.base_y_m, previous.yaw_deg),
            Pose2D(current.base_x_m, current.base_y_m, current.yaw_deg),
        )
        for sample_index, pose in enumerate(poses):
            body = OrientedBox(
                "forklift_body",
                pose.position,
                (2.2, 1.5),
                pose.yaw_deg,
                0.18,
                2.50,
            )
            for static in statics:
                if body.z_max <= static.z_min or static.z_max <= body.z_min:
                    continue
                check_count += 1
                clearance = box_separation_xy(body, static)
                minimum_clearance = min(minimum_clearance, clearance)
                if boxes_overlap_3d(body, static, margin_xy=0.05):
                    hits.append(
                        CollisionHit(
                            dynamic_name=body.name,
                            static_name=static.name,
                            sample_index=sample_index,
                            pose=pose,
                        )
                    )
    if math.isinf(minimum_clearance):
        minimum_clearance = 0.0
    return CollisionCertification(
        collision_check_count=check_count,
        minimum_body_clearance_m=round(minimum_clearance, 6),
        forbidden_collision_count=len(hits),
        collisions=tuple(hits),
    )


def assert_timeline_collision_safe(timeline) -> CollisionCertification:
    certification = certify_timeline(timeline)
    if certification.collisions:
        first = certification.collisions[0]
        raise RuntimeError(
            "forbidden swept collision: "
            f"{first.dynamic_name} vs {first.static_name} at "
            f"({first.pose.x_m:.3f}, {first.pose.y_m:.3f}, {first.pose.yaw_deg:.2f})"
        )
    return certification


def assert_frame_transition_safe(previous, current, scenario: str) -> None:
    """Re-check the imminent kinematic transform before authoring it to USD."""
    hits = find_forbidden_collisions(
        Pose2D(previous.base_x_m, previous.base_y_m, previous.yaw_deg),
        Pose2D(current.base_x_m, current.base_y_m, current.yaw_deg),
        warehouse_static_boxes(scenario),
    )
    if hits:
        first = hits[0]
        raise RuntimeError(
            "forbidden frame transition: "
            f"{first.dynamic_name} vs {first.static_name} before frame {current.frame}"
        )
