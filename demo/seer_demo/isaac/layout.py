"""Pure geometry and physics-role contract for the warehouse evidence scene."""

from __future__ import annotations

from dataclasses import dataclass
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


CONTAINER_FLOOR_TOP_M = 0.12
CONVEYOR_SUPPORT_TOP_M = 0.78
PAYLOAD_SUPPORT_CLEARANCE_M = 0.005
PAYLOAD_ATTACHMENT_Z_OFFSET_M = 0.015
INSERTION_MAST_HEIGHT_M = 0.11
BACKGROUND_LOAD_LOCAL_POSITIONS = ((5.15, 0.82), (5.15, -0.82))


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
        # The conveyor begins at local x=-1.6. The chassis reaches 1.1 m
        # forward from its base; the forks alone enter the remaining gap.
        conveyor_near_edge_x = -1.6
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
        container=FacilityPose((0.5, 1.4, 0.0), 8.0),
        loading_dock=FacilityPose((2.0, 4.1, 0.0), 0.0),
        conveyor=FacilityPose((-6.0, -4.2, 0.0), -6.0),
        container_payload_local=(
            3.85,
            0.0,
            CONTAINER_FLOOR_TOP_M + PAYLOAD_SUPPORT_CLEARANCE_M,
        ),
        container_entry_local=(0.5, 0.0, 0.0),
        container_alignment_local=(2.2, 0.0, 0.0),
        container_exit_local=(-1.5, 0.0, 0.0),
        conveyor_payload_local=(
            -1.7,
            0.0,
            CONVEYOR_SUPPORT_TOP_M + PAYLOAD_SUPPORT_CLEARANCE_M,
        ),
        conveyor_alignment_local=(-3.3, 0.0, 0.0),
    )


def conveyor_geometry_specs() -> tuple[BoxGeometrySpec, ...]:
    """Return a fork-accessible conveyor with three pallet support lanes."""
    parts: list[BoxGeometrySpec] = [
        BoxGeometrySpec("SideRailLeft", "side_rail", (3.2, 0.10, 0.36), (0.0, -0.66, 0.30)),
        BoxGeometrySpec("SideRailRight", "side_rail", (3.2, 0.10, 0.36), (0.0, 0.66, 0.30)),
    ]
    for x_index, x_position in enumerate(-1.25 + index * 0.31 for index in range(9)):
        for lane_index, y_position in enumerate((-0.58, 0.0, 0.58)):
            parts.append(
                BoxGeometrySpec(
                    f"Roller{x_index:02d}_{lane_index}",
                    "support_roller",
                    (0.16, 0.12, 0.16),
                    (x_position, y_position, 0.70),
                )
            )
    for x_index, x_position in enumerate((-1.35, 1.35)):
        for y_index, y_position in enumerate((-0.66, 0.66)):
            parts.append(
                BoxGeometrySpec(
                    f"Leg{x_index}_{y_index}",
                    "support_leg",
                    (0.12, 0.12, 0.60),
                    (x_position, y_position, 0.30),
                )
            )
    return tuple(parts)


def static_physics_contract() -> tuple[StaticPhysicsSpec, ...]:
    return (
        StaticPhysicsSpec("ground", "/World/Ground"),
        StaticPhysicsSpec("warehouse_shell", "/World/Warehouse"),
        StaticPhysicsSpec("racks", "/World/Warehouse/Racks"),
        StaticPhysicsSpec("container", "/World/Container"),
        StaticPhysicsSpec("loading_dock", "/World/LoadingDock"),
        StaticPhysicsSpec("conveyor", "/World/Conveyor"),
        StaticPhysicsSpec("background_loads", "/World/BackgroundLoads"),
        StaticPhysicsSpec("obstacle", "/World/Obstacle"),
    )
