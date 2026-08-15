"""Pure-Python 2.5D collision checks for deterministic Isaac motion."""

from __future__ import annotations

from dataclasses import dataclass
import math


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
