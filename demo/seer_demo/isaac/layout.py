"""Pure geometry and physics-role contract for the warehouse evidence scene."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math


@dataclass(frozen=True, slots=True)
class FacilityPose:
    position: tuple[float, float, float]
    yaw_deg: float


@dataclass(frozen=True, slots=True)
class StaticPhysicsSpec:
    name: str
    prim_path: str
    collision_enabled: bool = True
    rigid_body_kind: str = "static"


@dataclass(frozen=True, slots=True)
class BoxGeometrySpec:
    name: str
    role: str
    size: tuple[float, float, float]
    position: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class CylinderGeometrySpec:
    name: str
    role: str
    radius: float
    height: float
    position: tuple[float, float, float]
    axis: str = "y"

    @property
    def primitive(self) -> str:
        return "cylinder"

    @property
    def size(self) -> tuple[float, float, float]:
        diameter = self.radius * 2.0
        if self.axis == "x":
            return (self.height, diameter, diameter)
        if self.axis == "y":
            return (diameter, self.height, diameter)
        if self.axis == "z":
            return (diameter, diameter, self.height)
        raise ValueError(f"unsupported cylinder axis: {self.axis}")


CONTAINER_FLOOR_TOP_M = 0.0
CONVEYOR_SUPPORT_TOP_M = 0.78
CONVEYOR_LENGTH_M = 3.4
CONVEYOR_WIDTH_M = 1.5
PAYLOAD_SUPPORT_CLEARANCE_M = 0.005
CONVEYOR_PAYLOAD_CLEARANCE_M = 0.0
PAYLOAD_ATTACHMENT_Z_OFFSET_M = 0.015
PAYLOAD_ATTACHMENT_X_OFFSET_M = 2.20
INSERTION_MAST_HEIGHT_M = -0.01
YELLOW_LANE_YAW_DEG = 0.0
CONTAINER_LENGTH_M = 7.5
CONTAINER_WIDTH_M = 3.4
CONTAINER_HEIGHT_M = 3.5
BACKGROUND_LOAD_LOCAL_POSITIONS = ((6.40, 1.02), (6.40, -1.02))
WAREHOUSE_EXTENT_M = (44.0, 28.0)
INTERVENTION_OBSTACLE_X_OFFSET_M = -1.35


@dataclass(frozen=True, slots=True)
class WarehouseLayoutSpec:
    container: FacilityPose
    loading_dock: FacilityPose
    conveyor: FacilityPose
    container_payload_local: tuple[float, float, float]
    container_entry_local: tuple[float, float, float]
    container_alignment_local: tuple[float, float, float]
    container_exit_local: tuple[float, float, float]
    conveyor_payload_local: tuple[float, float, float]
    conveyor_alignment_local: tuple[float, float, float]

    @property
    def container_payload_target(self) -> tuple[float, float, float]:
        return world_from_local(
            self.container.position,
            self.container.yaw_deg,
            self.container_payload_local,
        )

    @property
    def conveyor_payload_target(self) -> tuple[float, float, float]:
        return world_from_local(
            self.conveyor.position,
            self.conveyor.yaw_deg,
            self.conveyor_payload_local,
        )

    @property
    def conveyor_alignment_target(self) -> tuple[float, float, float]:
        return world_from_local(
            self.conveyor.position,
            self.conveyor.yaw_deg,
            self.conveyor_alignment_local,
        )

    @property
    def conveyor_body_clearance_m(self) -> float:
        # The chassis reaches 1.1 m forward from its base; only the fork and
        # carried pallet enter the remaining conveyor approach gap.
        conveyor_near_edge_x = -CONVEYOR_LENGTH_M / 2.0
        chassis_front_x = self.conveyor_alignment_local[0] + 1.1
        return round(conveyor_near_edge_x - chassis_front_x, 6)


def world_from_local(
    origin: tuple[float, float, float],
    yaw_deg: float,
    local: tuple[float, float, float],
) -> tuple[float, float, float]:
    radians = math.radians(yaw_deg)
    cosine, sine = math.cos(radians), math.sin(radians)
    return (
        origin[0] + cosine * local[0] - sine * local[1],
        origin[1] + sine * local[0] + cosine * local[1],
        origin[2] + local[2],
    )


def local_from_world(
    origin: tuple[float, float, float],
    yaw_deg: float,
    world: tuple[float, float, float],
) -> tuple[float, float, float]:
    radians = math.radians(yaw_deg)
    cosine, sine = math.cos(radians), math.sin(radians)
    dx, dy, dz = world[0] - origin[0], world[1] - origin[1], world[2] - origin[2]
    return (
        cosine * dx + sine * dy,
        -sine * dx + cosine * dy,
        dz,
    )


def warehouse_layout_spec() -> WarehouseLayoutSpec:
    return WarehouseLayoutSpec(
        container=FacilityPose((0.5, 1.4, 0.0), YELLOW_LANE_YAW_DEG),
        loading_dock=FacilityPose((2.0, 4.1, 0.0), YELLOW_LANE_YAW_DEG),
        conveyor=FacilityPose((-6.0, -4.2, 0.0), YELLOW_LANE_YAW_DEG),
        container_payload_local=(
            4.85,
            0.0,
            CONTAINER_FLOOR_TOP_M + PAYLOAD_SUPPORT_CLEARANCE_M,
        ),
        container_entry_local=(0.5, 0.0, 0.0),
        # Stop with the fork tips 0.05 m behind the pallet envelope.  Fork
        # insertion starts only after perception/recovery has accepted pose.
        container_alignment_local=(0.85, 0.0, 0.0),
        container_exit_local=(-1.5, 0.0, 0.0),
        conveyor_payload_local=(
            -1.05,
            0.0,
            CONVEYOR_SUPPORT_TOP_M + CONVEYOR_PAYLOAD_CLEARANCE_M,
        ),
        # Align the carried pallet over the support target before release;
        # release therefore changes attachment state, never world position.
        conveyor_alignment_local=(
            -1.05 - PAYLOAD_ATTACHMENT_X_OFFSET_M,
            0.0,
            0.0,
        ),
    )


@lru_cache(maxsize=1)
def conveyor_geometry_specs() -> tuple[BoxGeometrySpec | CylinderGeometrySpec, ...]:
    """Return a rigid roller conveyor with a fork-accessible approach."""
    parts: list[BoxGeometrySpec | CylinderGeometrySpec] = [
        BoxGeometrySpec(
            "SideRailLeft",
            "side_rail",
            (CONVEYOR_LENGTH_M, 0.12, 0.24),
            (0.0, -CONVEYOR_WIDTH_M / 2.0, 0.58),
        ),
        BoxGeometrySpec(
            "SideRailRight",
            "side_rail",
            (CONVEYOR_LENGTH_M, 0.12, 0.24),
            (0.0, CONVEYOR_WIDTH_M / 2.0, 0.58),
        ),
    ]
    roller_radius = 0.08
    roller_height = CONVEYOR_WIDTH_M - 0.24
    for x_index, x_position in enumerate(-1.48 + index * 0.296 for index in range(11)):
        parts.append(
            CylinderGeometrySpec(
                f"Roller{x_index:02d}",
                "support_roller",
                roller_radius,
                roller_height,
                (x_position, 0.0, CONVEYOR_SUPPORT_TOP_M - roller_radius),
            )
        )
    for x_index, x_position in enumerate((-1.35, 0.0, 1.35)):
        parts.append(
            BoxGeometrySpec(
                f"CrossMember{x_index}",
                "cross_member",
                (0.12, CONVEYOR_WIDTH_M, 0.12),
                (x_position, 0.0, 0.45),
            )
        )
    for x_index, x_position in enumerate((-1.35, 1.35)):
        for y_index, y_position in enumerate((-0.67, 0.67)):
            parts.append(
                BoxGeometrySpec(
                    f"Leg{x_index}_{y_index}",
                    "support_leg",
                    (0.12, 0.12, 0.60),
                    (x_position, y_position, 0.30),
                )
            )
    return tuple(parts)


@lru_cache(maxsize=1)
def forklift_lift_geometry_specs() -> tuple[BoxGeometrySpec, ...]:
    """Geometry below ForkTilt; scene and collision guard share these values."""
    return (
        BoxGeometrySpec("Carrier", "carrier", (0.18, 0.92, 0.40), (1.12, 0.0, 0.25)),
        BoxGeometrySpec("ForkLeft", "fork", (1.75, 0.13, 0.10), (1.75, 0.32, 0.08)),
        BoxGeometrySpec("ForkRight", "fork", (1.75, 0.13, 0.10), (1.75, -0.32, 0.08)),
    )


@lru_cache(maxsize=1)
def active_payload_geometry_specs() -> tuple[BoxGeometrySpec, ...]:
    """Geometry below ActivePayload; shared by USD authoring and guard."""
    parts: list[BoxGeometrySpec] = []
    for index, y_position in enumerate((-0.52, -0.26, 0.0, 0.26, 0.52)):
        parts.append(
            BoxGeometrySpec(
                f"Deck{index}",
                "deck",
                (1.15, 0.18, 0.09),
                (0.0, y_position, 0.16),
            )
        )
    for index, y_position in enumerate((-0.58, 0.0, 0.58)):
        parts.append(
            BoxGeometrySpec(
                f"Runner{index}",
                "runner",
                (1.15, 0.12, 0.10),
                (0.0, y_position, 0.05),
            )
        )
    # Cargo rests on the deck top (local z=0.205) instead of intersecting it.
    for index, (x_position, y_position) in enumerate(
        ((-0.28, -0.25), (-0.28, 0.25), (0.28, -0.25), (0.28, 0.25))
    ):
        parts.append(
            BoxGeometrySpec(
                f"Cargo{index}",
                "cargo",
                (0.50, 0.42, 0.55),
                (x_position, y_position, 0.48),
            )
        )
    return tuple(parts)


def warehouse_shell_geometry_specs() -> tuple[BoxGeometrySpec, ...]:
    width, depth = WAREHOUSE_EXTENT_M
    parts = [
        BoxGeometrySpec(
            "BackWall",
            "wall",
            (width - 1.0, 0.22, 7.5),
            (0.0, depth / 2 - 0.5, 3.75),
        ),
        BoxGeometrySpec(
            "SideWall",
            "wall",
            (0.22, depth - 1.0, 7.5),
            (width / 2 - 0.5, 0.0, 3.75),
        ),
    ]
    for index, x_position in enumerate(range(-18, 19, 6)):
        parts.append(
            BoxGeometrySpec(
                f"CeilingBeam{index}",
                "ceiling_beam",
                (0.18, depth - 1.0, 0.26),
                (float(x_position), 0.0, 7.0),
            )
        )
    return tuple(parts)


def loading_dock_geometry_specs() -> tuple[BoxGeometrySpec, ...]:
    return (
        BoxGeometrySpec("Deck", "deck", (6.0, 1.1, 0.22), (0.0, 0.0, 0.11)),
        BoxGeometrySpec("Bumper", "bumper", (0.30, 1.1, 0.52), (-3.0, 0.0, 0.26)),
    )


def container_geometry_specs() -> tuple[BoxGeometrySpec, ...]:
    half_width = CONTAINER_WIDTH_M / 2.0
    half_height = CONTAINER_HEIGHT_M / 2.0
    half_length = CONTAINER_LENGTH_M / 2.0
    return (
        BoxGeometrySpec(
            "Floor",
            "support_floor",
            (CONTAINER_LENGTH_M, CONTAINER_WIDTH_M, 0.12),
            (half_length, 0.0, CONTAINER_FLOOR_TOP_M - 0.06),
        ),
        BoxGeometrySpec(
            "Back",
            "wall",
            (0.12, CONTAINER_WIDTH_M, CONTAINER_HEIGHT_M),
            (CONTAINER_LENGTH_M, 0.0, half_height),
        ),
        BoxGeometrySpec(
            "Left",
            "wall",
            (CONTAINER_LENGTH_M, 0.10, CONTAINER_HEIGHT_M),
            (half_length, half_width, half_height),
        ),
        BoxGeometrySpec(
            "RightTopRail",
            "top_rail",
            (CONTAINER_LENGTH_M, 0.10, 0.12),
            (half_length, -half_width, CONTAINER_HEIGHT_M - 0.06),
        ),
        BoxGeometrySpec(
            "RoofBackRail",
            "top_rail",
            (0.12, CONTAINER_WIDTH_M, 0.12),
            (CONTAINER_LENGTH_M - 0.06, 0.0, CONTAINER_HEIGHT_M - 0.06),
        ),
        BoxGeometrySpec(
            "DoorFrame0",
            "door_frame",
            (0.12, 0.12, CONTAINER_HEIGHT_M),
            (0.0, -half_width + 0.18, half_height),
        ),
        BoxGeometrySpec(
            "DoorFrame1",
            "door_frame",
            (0.12, 0.12, CONTAINER_HEIGHT_M),
            (0.0, half_width - 0.18, half_height),
        ),
    )


def background_load_geometry_specs() -> tuple[BoxGeometrySpec, ...]:
    parts: list[BoxGeometrySpec] = []
    for index, (x_position, y_position) in enumerate(BACKGROUND_LOAD_LOCAL_POSITIONS):
        parts.extend(
            (
                BoxGeometrySpec(
                    f"Load{index}_Pallet",
                    "pallet",
                    (1.0, 0.75, 0.12),
                    (x_position, y_position, 0.12),
                ),
                BoxGeometrySpec(
                    f"Load{index}_Cargo",
                    "cargo",
                    (0.80, 0.60, 0.75),
                    (x_position, y_position, 0.55),
                ),
            )
        )
    return tuple(parts)


def static_physics_contract(
    scenario: str | None = None,
) -> tuple[StaticPhysicsSpec, ...]:
    """Return active static roots; hidden fault geometry has no collider."""
    if scenario not in {None, "normal", "recovery", "intervention"}:
        raise ValueError(f"unknown scenario: {scenario}")
    common = (
        StaticPhysicsSpec("ground", "/World/Ground"),
        StaticPhysicsSpec("warehouse_shell", "/World/Warehouse"),
        StaticPhysicsSpec("racks", "/World/Warehouse/Racks"),
        StaticPhysicsSpec("container", "/World/Container"),
        StaticPhysicsSpec("loading_dock", "/World/LoadingDock"),
        StaticPhysicsSpec("conveyor", "/World/Conveyor"),
        StaticPhysicsSpec("background_loads", "/World/BackgroundLoads"),
    )
    if scenario in {None, "intervention"}:
        return common + (StaticPhysicsSpec("obstacle", "/World/Obstacle"),)
    return common
