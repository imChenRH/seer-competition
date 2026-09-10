"""Z-up OpenUSD warehouse scene for the deterministic Isaac demonstration."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from .layout import (
    CONTAINER_LENGTH_M,
    INTERVENTION_OBSTACLE_X_OFFSET_M,
    PAYLOAD_ATTACHMENT_Z_OFFSET_M,
    PAYLOAD_ATTACHMENT_X_OFFSET_M,
    WAREHOUSE_EXTENT_M,
    active_payload_geometry_specs,
    background_load_geometry_specs,
    CylinderGeometrySpec,
    container_geometry_specs,
    conveyor_geometry_specs,
    forklift_lift_geometry_specs,
    intervention_obstacle_geometry_specs,
    local_from_world,
    loading_dock_geometry_specs,
    static_physics_contract,
    warehouse_layout_spec,
    warehouse_shell_geometry_specs,
)
from .timeline import FORKLIFT_PARTS, FrameState


PHYSICS_SCHEMA_APIS = (
    "PhysicsScene",
    "CollisionAPI",
    "RigidBodyAPI",
    "MassAPI",
    "FixedJoint",
)
FORK_POCKET_CENTERS_Y = (-0.32, 0.32)


@dataclass(frozen=True, slots=True)
class WarehouseAssetSpec:
    path: Path
    prim_name: str
    position: tuple[float, float, float]
    rotation_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass(frozen=True, slots=True)
class CameraPose:
    position: tuple[float, float, float]
    look_at: tuple[float, float, float]


CAMERA_FOCAL_LENGTH_MM = 13.0
CAMERA_HORIZONTAL_APERTURE_MM = 36.0
CAMERA_SAFE_MARGIN = 0.05
CAMERA_LOCAL_FORWARD_M = 8.0
CAMERA_LOCAL_SIDE_M = 2.6
CAMERA_LOCAL_HEIGHT_M = 4.5

_PAYLOAD_INTERACTION_PHASES = frozenset(
    {
        "precision_approach",
        "offset_detected",
        "pose_verified",
        "pose_revalidated",
        "occluded_view_1",
        "occluded_view_2",
        "occluded_view_3",
        "view_adjust_1",
        "view_adjust_2",
        "insert_forks",
        "lift_payload",
        "tilt_stabilize",
    }
)
_CONTAINER_CAMERA_PHASES = frozenset(
    {
        "enter_container",
        "precision_approach",
        "offset_detected",
        "lateral_realign",
        "pose_verified",
        "pose_revalidated",
        "occluded_view_1",
        "occluded_view_2",
        "occluded_view_3",
        "view_adjust_1",
        "view_adjust_2",
        "insert_forks",
        "lift_payload",
        "tilt_stabilize",
        "exit_container",
        "safe_retreat",
        "safety_stop",
    }
)


@dataclass(frozen=True, slots=True)
class PalletPartSpec:
    role: str
    size: tuple[float, float, float]
    position: tuple[float, float, float]
    color: tuple[float, float, float]


def pallet_part_specs() -> tuple[PalletPartSpec, ...]:
    """Build a pallet with two unobstructed, fork-aligned entry pockets."""
    wood = (0.48, 0.28, 0.10)
    return tuple(
        PalletPartSpec(spec.role, spec.size, spec.position, wood)
        for spec in active_payload_geometry_specs()
        if spec.role != "cargo"
    )


def physical_attachment_for_frame(frame: FrameState) -> bool:
    """Return the authored FixedJoint state for one evidence frame."""
    return bool(frame.payload_attached)


def attachment_joint_pose_for_frame(
    frame: FrameState,
) -> tuple[tuple[float, float, float], float]:
    """Return the coincident joint anchor expressed in the forklift frame."""
    local_position = local_from_world(
        (frame.base_x_m, frame.base_y_m, frame.base_z_m),
        frame.yaw_deg,
        (frame.payload_x_m, frame.payload_y_m, frame.payload_z_m),
    )
    local_yaw = (frame.payload_yaw_deg - frame.yaw_deg + 180.0) % 360.0 - 180.0
    return local_position, local_yaw


def yaw_degrees_from_quaternion_components(
    real: float,
    imaginary: tuple[float, float, float],
) -> float:
    """Extract normalized Z yaw without depending on a specific USD xform op."""
    x_value, y_value, z_value = (float(value) for value in imaginary)
    real_value = float(real)
    numerator = 2.0 * (real_value * z_value + x_value * y_value)
    denominator = 1.0 - 2.0 * (y_value * y_value + z_value * z_value)
    yaw = math.degrees(math.atan2(numerator, denominator))
    return (yaw + 180.0) % 360.0 - 180.0


def payload_dynamic_for_frame(frame: FrameState) -> bool:
    """Release the payload to physics only after conveyor placement begins."""
    return bool(frame.payload_placed and not frame.payload_attached)


def warehouse_rack_positions() -> tuple[tuple[float, float], ...]:
    return tuple((float(x), float(y)) for y in (-7.2, 7.2) for x in (-12, -6, 0, 6, 12))


def warehouse_asset_specs(asset_root: Path | str) -> tuple[WarehouseAssetSpec, ...]:
    root = Path(asset_root)
    values = (
        ("Props/materials/physics/physics_concrete.usda", "OfficialConcrete", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ("Props/materials/physics/physics_metal.usda", "OfficialMetal", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ("Props/materials/physics/physics_cardboard.usda", "OfficialCardboard", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ("Props/materials/physics/physics_rubber.usda", "OfficialRubber", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    )
    return tuple(
        WarehouseAssetSpec(root / relative, name, position, rotation)
        for relative, name, position, rotation in values
    )


def camera_pose_for_phase(phase: str) -> CameraPose:
    if phase in {"precision_approach", "offset_detected", "pose_verified", "pose_revalidated", "occluded_view_1", "occluded_view_2", "occluded_view_3", "view_adjust_1", "view_adjust_2"}:
        return CameraPose((7.5, 4.3, 4.8), (3.1, 1.7, 0.8))
    if phase in {"insert_forks", "lift_payload", "tilt_stabilize"}:
        return CameraPose((7.5, 4.3, 4.6), (3.1, 1.7, 0.85))
    if phase in {"prealign_conveyor", "align_conveyor", "place_payload"}:
        return CameraPose((1.2, -1.5, 4.8), (-6.8, -4.1, 0.75))
    if phase in {"safe_retreat", "safety_stop"}:
        return CameraPose((7.2, 3.8, 4.8), (-0.8, 1.2, 0.9))
    return CameraPose((6.0, 4.3, 4.8), (0.0, 1.3, 0.9))


def _normalized(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-9:
        raise ValueError("camera direction must be non-zero")
    return tuple(value / length for value in vector)


def _bounds_corners(
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        (x, y, z)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    )


def subject_world_corners(frame: FrameState) -> tuple[tuple[float, float, float], ...]:
    """Return a conservative rendered-subject envelope for camera fitting."""
    yaw = math.radians(frame.yaw_deg)
    cosine, sine = math.cos(yaw), math.sin(yaw)
    points: list[tuple[float, float, float]] = []
    for x, y, z in _bounds_corners((-1.10, -0.76, 0.0), (2.64, 0.76, 2.66)):
        points.append(
            (
                frame.base_x_m + cosine * x - sine * y,
                frame.base_y_m + sine * x + cosine * y,
                frame.base_z_m + z,
            )
        )
    if _payload_is_camera_subject(frame):
        payload_yaw = math.radians(frame.payload_yaw_deg)
        payload_cosine, payload_sine = math.cos(payload_yaw), math.sin(payload_yaw)
        for x, y, z in _bounds_corners((-0.58, -0.65, 0.0), (0.58, 0.65, 0.76)):
            points.append(
                (
                    frame.payload_x_m + payload_cosine * x - payload_sine * y,
                    frame.payload_y_m + payload_sine * x + payload_cosine * y,
                    frame.payload_z_m + z,
                )
            )
    return tuple(points)


def _payload_is_camera_subject(frame: FrameState) -> bool:
    if frame.payload_attached or frame.payload_placed:
        return True
    if frame.phase not in _PAYLOAD_INTERACTION_PHASES:
        return False
    horizontal_distance = math.hypot(
        frame.payload_x_m - frame.base_x_m,
        frame.payload_y_m - frame.base_y_m,
    )
    return horizontal_distance <= 6.0


def _subject_center_and_radius(
    frame: FrameState,
) -> tuple[tuple[float, float, float], float]:
    points = subject_world_corners(frame)
    minimum = tuple(min(point[index] for point in points) for index in range(3))
    maximum = tuple(max(point[index] for point in points) for index in range(3))
    center = tuple((minimum[index] + maximum[index]) / 2.0 for index in range(3))
    radius = max(math.dist(center, point) for point in points)
    return center, radius


def camera_pose_for_frame(frame: FrameState) -> CameraPose:
    center, _ = _subject_center_and_radius(frame)
    yaw = math.radians(frame.yaw_deg)
    forward = (math.cos(yaw), math.sin(yaw))
    left = (-math.sin(yaw), math.cos(yaw))
    position = (
        frame.base_x_m
        + forward[0] * CAMERA_LOCAL_FORWARD_M
        + left[0] * CAMERA_LOCAL_SIDE_M,
        frame.base_y_m
        + forward[1] * CAMERA_LOCAL_FORWARD_M
        + left[1] * CAMERA_LOCAL_SIDE_M,
        frame.base_z_m + CAMERA_LOCAL_HEIGHT_M,
    )
    if frame.phase in _CONTAINER_CAMERA_PHASES:
        container = warehouse_layout_spec().container
        back_wall_limit = container.position[0] + CONTAINER_LENGTH_M - 0.5
        position = (min(position[0], back_wall_limit), position[1], position[2])
    return CameraPose(position, center)


def camera_frame_margin(
    frame: FrameState,
    pose: CameraPose,
    *,
    aspect_ratio: float,
) -> float:
    """Project the subject envelope and return its smallest normalized edge gap."""
    if aspect_ratio <= 0.0:
        raise ValueError("aspect_ratio must be positive")
    forward = _normalized(
        tuple(pose.look_at[index] - pose.position[index] for index in range(3))
    )
    right = _normalized((forward[1], -forward[0], 0.0))
    true_up = (
        right[1] * forward[2],
        -right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    )
    tan_half_horizontal = CAMERA_HORIZONTAL_APERTURE_MM / (
        2.0 * CAMERA_FOCAL_LENGTH_MM
    )
    tan_half_vertical = tan_half_horizontal / aspect_ratio
    margins: list[float] = []
    for point in subject_world_corners(frame):
        delta = tuple(point[index] - pose.position[index] for index in range(3))
        depth = sum(delta[index] * forward[index] for index in range(3))
        if depth <= 0.0:
            return -1.0
        horizontal = sum(delta[index] * right[index] for index in range(3))
        vertical = sum(delta[index] * true_up[index] for index in range(3))
        screen_x = 0.5 + horizontal / (2.0 * depth * tan_half_horizontal)
        screen_y = 0.5 - vertical / (2.0 * depth * tan_half_vertical)
        margins.append(min(screen_x, 1.0 - screen_x, screen_y, 1.0 - screen_y))
    return min(margins)


def camera_poses_for_timeline(timeline) -> tuple[CameraPose, ...]:
    """Smooth phase-angle changes while preserving per-frame subject framing."""
    poses: list[CameraPose] = []
    alpha = min(1.0, 1.0 / max(1.0, timeline.fps * 1.25))
    previous_relative: tuple[float, float, float] | None = None
    for frame in timeline.frames:
        desired = camera_pose_for_frame(frame)
        desired_relative = tuple(
            desired.position[index] - desired.look_at[index] for index in range(3)
        )
        if previous_relative is None:
            relative = desired_relative
        else:
            relative = tuple(
                previous_relative[index]
                + (desired_relative[index] - previous_relative[index]) * alpha
                for index in range(3)
            )
        position = tuple(
            desired.look_at[index] + relative[index] for index in range(3)
        )
        pose = CameraPose(position, desired.look_at)
        margin = camera_frame_margin(frame, pose, aspect_ratio=16.0 / 9.0)
        while margin < CAMERA_SAFE_MARGIN:
            relative = tuple(
                pose.position[index] - pose.look_at[index] for index in range(3)
            )
            position = tuple(
                pose.look_at[index] + relative[index] * 1.08 for index in range(3)
            )
            pose = CameraPose(position, pose.look_at)
            margin = camera_frame_margin(frame, pose, aspect_ratio=16.0 / 9.0)
        poses.append(pose)
        previous_relative = tuple(
            pose.position[index] - pose.look_at[index] for index in range(3)
        )
    return tuple(poses)


def derive_kinematic_observation(
    *,
    base,
    lift,
    payload,
    yaw_deg: float,
    fork_tilt_deg: float,
    obstacle_visible: bool,
    base_speed_mps: float,
    physical_attachment_enabled: bool,
    payload_yaw_deg: float = 0.0,
) -> dict[str, object]:
    """Derive state from measured transforms/visibility, never scenario labels."""
    base_xyz = tuple(float(value) for value in base)
    lift_xyz = tuple(float(value) for value in lift)
    payload_xyz = tuple(float(value) for value in payload)
    mast_height = lift_xyz[2] - base_xyz[2]
    relative_payload = local_from_world(
        base_xyz,
        float(yaw_deg),
        (
            payload_xyz[0],
            payload_xyz[1],
            payload_xyz[2] - mast_height,
        ),
    )
    geometry_attached = (
        abs(relative_payload[0] - PAYLOAD_ATTACHMENT_X_OFFSET_M) <= 0.03
        and abs(relative_payload[1]) <= 0.03
        and abs(relative_payload[2] - PAYLOAD_ATTACHMENT_Z_OFFSET_M) <= 0.03
        and abs(
            (float(payload_yaw_deg) - float(yaw_deg) + 180.0) % 360.0 - 180.0
        ) <= 0.5
    )
    payload_attached = geometry_attached and bool(physical_attachment_enabled)
    layout = warehouse_layout_spec()
    base_in_container = local_from_world(
        layout.container.position,
        layout.container.yaw_deg,
        base_xyz,
    )
    placement = layout.conveyor_payload_target
    placement_error = (
        (payload_xyz[0] - placement[0]) ** 2
        + (payload_xyz[1] - placement[1]) ** 2
    ) ** 0.5
    payload_support_error = abs(payload_xyz[2] - placement[2])
    payload_placed = (
        not payload_attached
        and placement_error <= 0.03
        and payload_support_error <= 0.03
    )
    payload_supported = (
        payload_placed
        and placement_error <= 0.02
        and payload_support_error <= 0.005
    )
    stopped = abs(float(base_speed_mps)) <= 0.01
    pallet_error = 0.0 if payload_attached else relative_payload[1]
    alignment_target = layout.container_alignment_local
    precision_alignment_error = (
        (base_in_container[0] - alignment_target[0]) ** 2
        + (base_in_container[1] - alignment_target[1]) ** 2
    ) ** 0.5
    return {
        "base_x_m": round(base_xyz[0], 6),
        "base_y_m": round(base_xyz[1], 6),
        "base_z_m": round(base_xyz[2], 6),
        "yaw_deg": round(float(yaw_deg), 6),
        "base_speed_mps": round(float(base_speed_mps), 6),
        "mast_height_m": round(mast_height, 6),
        "fork_tilt_deg": round(float(fork_tilt_deg), 6),
        "payload_x_m": round(payload_xyz[0], 6),
        "payload_y_m": round(payload_xyz[1], 6),
        "payload_z_m": round(payload_xyz[2], 6),
        "payload_yaw_deg": round(float(payload_yaw_deg), 6),
        "payload_attached": payload_attached,
        "physical_attachment_enabled": bool(physical_attachment_enabled),
        "payload_placed": payload_placed,
        "payload_supported": payload_supported,
        "payload_support_error_m": round(payload_support_error, 6),
        "pallet_lateral_error_m": round(pallet_error, 6),
        "camera_lateral_offset_m": round(base_in_container[1], 6),
        "precision_alignment_error_m": round(precision_alignment_error, 6),
        "obstacle_visible": bool(obstacle_visible),
        "stopped": stopped,
        "safe_retreat_complete": (
            base_xyz[0] <= -0.9 and not payload_attached
        ),
        "aligned_with_conveyor": (
            abs(base_xyz[0] - layout.conveyor_alignment_target[0]) <= 0.08
            and abs(base_xyz[1] - layout.conveyor_alignment_target[1]) <= 0.08
            and abs(float(yaw_deg) - layout.conveyor.yaw_deg) <= 0.5
        ),
    }


@dataclass(slots=True)
class SceneHandles:
    stage: Any
    forklift_root: Any
    lift_root: Any
    fork_tilt_root: Any
    payload_root: Any
    payload_body: Any
    payload_joint: Any
    obstacle_root: Any
    beacon: Any
    referenced_assets: tuple[str, ...]
    static_collision_prims: tuple[str, ...]
    payload_released: bool = False


def build_scene(
    output_path: Path | str,
    scenario: str,
    warehouse_asset_root: Path | str | None = None,
) -> SceneHandles:
    import omni.usd
    from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdPhysics, UsdShade

    context = omni.usd.get_context()
    context.new_stage()
    stage = context.get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = stage.DefinePrim("/World", "Xform")
    stage.SetDefaultPrim(world)
    physics_scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    physics_scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    physics_scene.CreateGravityMagnitudeAttr(9.81)

    materials: dict[str, Any] = {}
    layout = warehouse_layout_spec()

    def preview_material(name: str, color, *, metallic=0.0, roughness=0.55):
        material = UsdShade.Material.Define(stage, f"/World/Looks/{name}")
        shader = UsdShade.Shader.Define(stage, f"/World/Looks/{name}/PreviewSurface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(metallic))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        materials[name] = material

    preview_material("Concrete", (0.17, 0.20, 0.23), roughness=0.82)
    preview_material("WarehouseSteel", (0.19, 0.24, 0.28), metallic=0.72, roughness=0.30)
    preview_material("RackOrange", (0.92, 0.32, 0.04), metallic=0.42, roughness=0.32)
    preview_material("SafetyYellow", (0.96, 0.70, 0.03), metallic=0.12, roughness=0.40)
    preview_material("Cardboard", (0.57, 0.36, 0.16), roughness=0.88)

    def box(path, size, position, color, opacity=1.0, material_name=None, collision=True):
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(1.0)
        common = UsdGeom.XformCommonAPI(cube)
        common.SetScale(Gf.Vec3f(*size))
        common.SetTranslate(Gf.Vec3d(*position))
        cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        if opacity < 1.0:
            cube.CreateDisplayOpacityAttr([opacity])
        if material_name is not None:
            UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(materials[material_name])
        if collision:
            UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
        return cube.GetPrim()

    def cylinder(
        path,
        radius,
        height,
        position,
        color,
        *,
        axis="y",
        material_name=None,
        collision=True,
    ):
        shape = UsdGeom.Cylinder.Define(stage, path)
        shape.CreateRadiusAttr(float(radius))
        shape.CreateHeightAttr(float(height))
        shape.CreateAxisAttr(getattr(UsdGeom.Tokens, axis))
        UsdGeom.XformCommonAPI(shape).SetTranslate(Gf.Vec3d(*position))
        shape.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        if material_name is not None:
            UsdShade.MaterialBindingAPI.Apply(shape.GetPrim()).Bind(materials[material_name])
        if collision:
            UsdPhysics.CollisionAPI.Apply(shape.GetPrim())
        return shape.GetPrim()

    # Expanded warehouse floor, aisle markings and shell.
    width, depth = WAREHOUSE_EXTENT_M
    box("/World/Ground", (width, depth, 0.10), (0.0, 0.0, -0.05), (0.16, 0.19, 0.23), material_name="Concrete")
    for x in range(-20, 21, 2):
        box(f"/World/Grid/X_{x+20}", (0.018, depth - 1.0, 0.012), (float(x), 0.0, 0.012), (0.28, 0.32, 0.37), collision=False)
    for y in range(-12, 13, 2):
        box(f"/World/Grid/Y_{y+12}", (width - 2.0, 0.018, 0.012), (0.0, float(y), 0.012), (0.28, 0.32, 0.37), collision=False)
    for spec in warehouse_shell_geometry_specs():
        color = (0.12, 0.15, 0.18) if spec.role == "ceiling_beam" else (0.19, 0.23, 0.27)
        box(
            f"/World/Warehouse/{spec.name}",
            spec.size,
            spec.position,
            color,
            material_name="WarehouseSteel",
        )
    for index, y in enumerate((-3.3, 3.3)):
        box(f"/World/Safety/MainLane{index}", (width - 5.0, 0.08, 0.025), (0.0, y, 0.025), (0.95, 0.75, 0.06), material_name="SafetyYellow", collision=False)
    box("/World/Safety/ExitLaneLeft", (10.0, 0.07, 0.025), (-1.0, 1.55, 0.025), (0.95, 0.75, 0.06), collision=False)
    box("/World/Safety/ExitLaneRight", (10.0, 0.07, 0.025), (-1.0, -1.55, 0.025), (0.95, 0.75, 0.06), collision=False)

    # Programmatic pallet racks make the scene useful even without optional NVIDIA assets.
    for rack_index, (rack_x, rack_y) in enumerate(warehouse_rack_positions()):
        rack_path = f"/World/Warehouse/Racks/Rack{rack_index:02d}"
        for post_index, (dx, dy) in enumerate(((-1.85, -0.58), (-1.85, 0.58), (1.85, -0.58), (1.85, 0.58))):
            box(f"{rack_path}/Post{post_index}", (0.12, 0.12, 4.8), (rack_x + dx, rack_y + dy, 2.4), (0.18, 0.22, 0.25), material_name="WarehouseSteel")
        for level_index, height in enumerate((0.65, 2.05, 3.45, 4.75)):
            box(f"{rack_path}/Beam{level_index}A", (3.9, 0.12, 0.16), (rack_x, rack_y - 0.58, height), (0.92, 0.32, 0.04), material_name="RackOrange")
            box(f"{rack_path}/Beam{level_index}B", (3.9, 0.12, 0.16), (rack_x, rack_y + 0.58, height), (0.92, 0.32, 0.04), material_name="RackOrange")
        for load_index, height in enumerate((0.86, 2.26, 3.66)):
            color = (0.55 + 0.05 * (rack_index % 3), 0.36, 0.16)
            box(f"{rack_path}/Load{load_index}", (1.45, 0.92, 0.86), (rack_x, rack_y, height + 0.40), color, material_name="Cardboard")

    referenced_assets: list[str] = []
    physics_materials: dict[str, Any] = {}
    if warehouse_asset_root is not None:
        for spec in warehouse_asset_specs(warehouse_asset_root):
            if not spec.path.is_file():
                continue
            prim = stage.OverridePrim(f"/World/PhysicsMaterials/{spec.prim_name}")
            prim.GetReferences().AddReference(str(spec.path))
            physics_materials[spec.prim_name] = UsdShade.Material(prim)
            referenced_assets.append(str(spec.path))

    def bind_physics(path: str, material_name: str) -> None:
        material = physics_materials.get(material_name)
        prim = stage.GetPrimAtPath(path)
        if material is not None and prim.IsValid():
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(material, materialPurpose="physics")

    # The loading dock remains static and axis-aligned while the container is
    # deliberately yawed, making alignment a visible part of the task.
    loading_dock_root = stage.DefinePrim("/World/LoadingDock", "Xform")
    loading_dock_api = UsdGeom.XformCommonAPI(loading_dock_root)
    loading_dock_api.SetTranslate(Gf.Vec3d(*layout.loading_dock.position))
    loading_dock_api.SetRotate(
        Gf.Vec3f(0.0, 0.0, layout.loading_dock.yaw_deg),
        UsdGeom.XformCommonAPI.RotationOrderXYZ,
    )
    for spec in loading_dock_geometry_specs():
        box(
            f"/World/LoadingDock/{spec.name}",
            spec.size,
            spec.position,
            (0.90, 0.62, 0.04) if spec.role == "bumper" else (0.30, 0.34, 0.38),
            material_name="SafetyYellow" if spec.role == "bumper" else "WarehouseSteel",
        )

    # Open container uses local Z as height; front is open at local x=0.
    container_root = stage.DefinePrim("/World/Container", "Xform")
    container_api = UsdGeom.XformCommonAPI(container_root)
    container_api.SetTranslate(Gf.Vec3d(*layout.container.position))
    container_api.SetRotate(
        Gf.Vec3f(0.0, 0.0, layout.container.yaw_deg),
        UsdGeom.XformCommonAPI.RotationOrderXYZ,
    )
    # Camera-side panels are structural cutaways; top rails preserve the silhouette.
    for spec in container_geometry_specs():
        color = {
            "support_floor": (0.31, 0.34, 0.37),
            "wall": (0.55, 0.22, 0.14),
            "top_rail": (0.50, 0.20, 0.13),
            "door_frame": (0.75, 0.33, 0.16),
        }[spec.role]
        box(f"/World/Container/{spec.name}", spec.size, spec.position, color)

    # The conveyor is farther away, laterally offset and counter-yawed.
    conveyor_root = stage.DefinePrim("/World/Conveyor", "Xform")
    conveyor_api = UsdGeom.XformCommonAPI(conveyor_root)
    conveyor_api.SetTranslate(Gf.Vec3d(*layout.conveyor.position))
    conveyor_api.SetRotate(
        Gf.Vec3f(0.0, 0.0, layout.conveyor.yaw_deg),
        UsdGeom.XformCommonAPI.RotationOrderXYZ,
    )
    for spec in conveyor_geometry_specs():
        path = f"/World/Conveyor/{spec.name}"
        if isinstance(spec, CylinderGeometrySpec):
            cylinder(
                path,
                spec.radius,
                spec.height,
                spec.position,
                (0.45, 0.52, 0.58),
                axis=spec.axis,
                material_name="WarehouseSteel",
            )
        else:
            box(
                path,
                spec.size,
                spec.position,
                (0.52, 0.58, 0.63),
                material_name="WarehouseSteel",
            )
    target_root = stage.DefinePrim("/World/Visuals/ConveyorTarget", "Xform")
    target_api = UsdGeom.XformCommonAPI(target_root)
    target_api.SetTranslate(Gf.Vec3d(*layout.conveyor.position))
    target_api.SetRotate(
        Gf.Vec3f(0.0, 0.0, layout.conveyor.yaw_deg),
        UsdGeom.XformCommonAPI.RotationOrderXYZ,
    )
    box(
        "/World/Visuals/ConveyorTarget/Pad",
        (0.95, 1.15, 0.012),
        layout.conveyor_payload_local,
        (0.10, 0.65, 0.42),
        collision=False,
    )

    # Forklift is one root with local child geometry. Lift is the only moving child group.
    forklift_root = stage.DefinePrim("/World/Forklift", "Xform")
    forklift_body = UsdPhysics.RigidBodyAPI.Apply(forklift_root)
    forklift_body.CreateKinematicEnabledAttr(True)
    UsdPhysics.MassAPI.Apply(forklift_root).CreateMassAttr(3200.0)
    stage.DefinePrim("/World/Forklift/Body", "Xform")
    for name, spec in FORKLIFT_PARTS.items():
        path = f"/World/Forklift/Body/{name}"
        if spec.primitive == "cylinder":
            cylinder(
                path,
                spec.size[2] / 2.0,
                spec.size[1],
                spec.local_position,
                spec.color,
                axis=spec.axis,
            )
        else:
            box(path, spec.size, spec.local_position, spec.color)
    lift_root = stage.DefinePrim("/World/Forklift/Lift", "Xform")
    fork_tilt_root = stage.DefinePrim("/World/Forklift/Lift/ForkTilt", "Xform")
    for spec in forklift_lift_geometry_specs():
        box(
            f"/World/Forklift/Lift/ForkTilt/{spec.name}",
            spec.size,
            spec.position,
            (0.25, 0.29, 0.34) if spec.role == "carrier" else (0.13, 0.15, 0.18),
        )
    beacon = box("/World/Forklift/SafetyBeacon", (0.18, 0.18, 0.25), (-0.10, 0.0, 2.35), (0.10, 0.75, 0.30))

    # Active pallet/load is deliberately a separate root so its coupling is explicit.
    payload_root = stage.DefinePrim("/World/ActivePayload", "Xform")
    payload_body = UsdPhysics.RigidBodyAPI.Apply(payload_root)
    payload_body.CreateKinematicEnabledAttr(True)
    UsdPhysics.MassAPI.Apply(payload_root).CreateMassAttr(450.0)
    for index, part in enumerate(pallet_part_specs()):
        box(
            f"/World/ActivePayload/Pallet/{part.role.title()}{index}",
            part.size,
            part.position,
            part.color,
        )
    for spec in active_payload_geometry_specs():
        if spec.role == "cargo":
            box(
                f"/World/ActivePayload/Cargo/{spec.name}",
                spec.size,
                spec.position,
                (0.72, 0.49, 0.22),
            )

    payload_joint = UsdPhysics.FixedJoint.Define(stage, "/World/Constraints/PayloadAttachment")
    payload_joint.CreateBody0Rel().SetTargets([Sdf.Path("/World/Forklift")])
    payload_joint.CreateBody1Rel().SetTargets([Sdf.Path("/World/ActivePayload")])
    payload_joint.CreateLocalPos0Attr(Gf.Vec3f(0.0, 0.0, 0.0))
    payload_joint.CreateLocalPos1Attr(Gf.Vec3f(0.0, 0.0, 0.0))
    payload_joint.CreateLocalRot0Attr(Gf.Quatf(1.0))
    payload_joint.CreateLocalRot1Attr(Gf.Quatf(1.0))
    payload_joint.CreateJointEnabledAttr(False)

    # Background pallets show the container is a multi-load task, not an isolated cube.
    background_root = stage.DefinePrim("/World/BackgroundLoads", "Xform")
    background_api = UsdGeom.XformCommonAPI(background_root)
    background_api.SetTranslate(Gf.Vec3d(*layout.container.position))
    background_api.SetRotate(
        Gf.Vec3f(0.0, 0.0, layout.container.yaw_deg),
        UsdGeom.XformCommonAPI.RotationOrderXYZ,
    )
    for spec in background_load_geometry_specs():
        load_index, part = spec.name.split("_", 1)
        box(
            f"/World/BackgroundLoads/{load_index}/{part}",
            spec.size,
            spec.position,
            (0.42, 0.24, 0.09) if spec.role == "pallet" else (0.35, 0.55, 0.72),
        )

    obstacle_root = stage.DefinePrim("/World/Obstacle", "Xform")
    obstacle_collision = scenario == "intervention"
    obstacle_colors = ((0.78, 0.16, 0.12), (0.92, 0.42, 0.08))
    for spec, color in zip(
        intervention_obstacle_geometry_specs(),
        obstacle_colors,
    ):
        box(
            f"/World/Obstacle/{spec.name}",
            spec.size,
            spec.position,
            color,
            collision=obstacle_collision,
        )
    obstacle_position = layout.container_payload_target
    UsdGeom.XformCommonAPI(obstacle_root).SetTranslate(
        Gf.Vec3d(
            obstacle_position[0] + INTERVENTION_OBSTACLE_X_OFFSET_M,
            obstacle_position[1],
            0.0,
        )
    )
    imageable = UsdGeom.Imageable(obstacle_root)
    if scenario == "intervention":
        imageable.MakeVisible()
    else:
        imageable.MakeInvisible()

    bind_physics("/World/Ground", "OfficialConcrete")
    bind_physics("/World/Warehouse/Racks", "OfficialMetal")
    bind_physics("/World/ActivePayload", "OfficialCardboard")
    bind_physics("/World/BackgroundLoads", "OfficialCardboard")
    bind_physics("/World/Forklift", "OfficialMetal")
    for wheel_name in ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"):
        bind_physics(f"/World/Forklift/Body/{wheel_name}", "OfficialRubber")

    static_collision_prims: list[str] = []
    for spec in static_physics_contract(scenario):
        root = stage.GetPrimAtPath(spec.prim_path)
        if not root.IsValid():
            raise RuntimeError(f"static physics root missing: {spec.prim_path}")
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            if path != spec.prim_path and not path.startswith(spec.prim_path + "/"):
                continue
            if prim.GetTypeName() not in {"Cube", "Cylinder"}:
                continue
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                raise RuntimeError(f"static collision missing: {path}")
            static_collision_prims.append(path)

    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(500.0)
    key = UsdLux.RectLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(18000.0)
    key.CreateWidthAttr(14.0)
    key.CreateHeightAttr(7.0)
    UsdGeom.XformCommonAPI(key).SetTranslate(Gf.Vec3d(-1.0, -2.0, 9.0))
    for index, x in enumerate((-12.0, 0.0, 12.0)):
        strip = UsdLux.RectLight.Define(stage, f"/World/Lights/Aisle{index}")
        strip.CreateIntensityAttr(3500.0)
        strip.CreateWidthAttr(5.0)
        strip.CreateHeightAttr(1.0)
        UsdGeom.XformCommonAPI(strip).SetTranslate(Gf.Vec3d(x, 0.0, 6.5))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage.GetRootLayer().Export(str(output))
    return SceneHandles(
        stage=stage,
        forklift_root=forklift_root,
        lift_root=lift_root,
        fork_tilt_root=fork_tilt_root,
        payload_root=payload_root,
        payload_body=payload_body,
        payload_joint=payload_joint,
        obstacle_root=obstacle_root,
        beacon=beacon,
        referenced_assets=tuple(referenced_assets),
        static_collision_prims=tuple(sorted(set(static_collision_prims))),
    )


def apply_frame(handles: SceneHandles, frame: FrameState) -> None:
    from pxr import Gf, Usd, UsdGeom

    base_value = Gf.Vec3d(frame.base_x_m, frame.base_y_m, frame.base_z_m)
    lift_value = Gf.Vec3d(0.0, 0.0, frame.mast_height_m)
    tilt_value = Gf.Vec3f(0.0, frame.fork_tilt_deg, 0.0)
    payload_value = Gf.Vec3d(frame.payload_x_m, frame.payload_y_m, frame.payload_z_m)
    payload_rotation_value = Gf.Vec3f(0.0, 0.0, frame.payload_yaw_deg)
    base_api = UsdGeom.XformCommonAPI(handles.forklift_root)
    lift_api = UsdGeom.XformCommonAPI(handles.lift_root)
    tilt_api = UsdGeom.XformCommonAPI(handles.fork_tilt_root)
    payload_api = UsdGeom.XformCommonAPI(handles.payload_root)
    base_api.SetTranslate(base_value)
    base_api.SetRotate(
        Gf.Vec3f(0.0, 0.0, frame.yaw_deg),
        UsdGeom.XformCommonAPI.RotationOrderXYZ,
    )
    lift_api.SetTranslate(lift_value)
    tilt_api.SetRotate(
        tilt_value,
        UsdGeom.XformCommonAPI.RotationOrderXYZ,
    )
    write_payload_transform = not handles.payload_released
    if write_payload_transform:
        payload_api.SetTranslate(payload_value)
        payload_api.SetRotate(
            payload_rotation_value,
            UsdGeom.XformCommonAPI.RotationOrderXYZ,
        )
    sample_time = Usd.TimeCode(frame.sim_time_s)
    handles.forklift_root.GetAttribute("xformOp:translate").Set(base_value, sample_time)
    handles.forklift_root.GetAttribute("xformOp:rotateXYZ").Set(
        Gf.Vec3f(0.0, 0.0, frame.yaw_deg), sample_time
    )
    handles.lift_root.GetAttribute("xformOp:translate").Set(lift_value, sample_time)
    handles.fork_tilt_root.GetAttribute("xformOp:rotateXYZ").Set(tilt_value, sample_time)
    if write_payload_transform:
        handles.payload_root.GetAttribute("xformOp:translate").Set(
            payload_value, sample_time
        )
        handles.payload_root.GetAttribute("xformOp:rotateXYZ").Set(
            payload_rotation_value, sample_time
        )
    attachment_enabled = physical_attachment_for_frame(frame)
    joint_position, joint_yaw_deg = attachment_joint_pose_for_frame(frame)
    joint_half_yaw = math.radians(joint_yaw_deg) / 2.0
    joint_rotation = Gf.Quatf(
        math.cos(joint_half_yaw),
        Gf.Vec3f(0.0, 0.0, math.sin(joint_half_yaw)),
    )
    local_pos0 = handles.payload_joint.GetLocalPos0Attr()
    local_rot0 = handles.payload_joint.GetLocalRot0Attr()
    local_pos0.Set(Gf.Vec3f(*joint_position))
    local_pos0.Set(Gf.Vec3f(*joint_position), sample_time)
    local_rot0.Set(joint_rotation)
    local_rot0.Set(joint_rotation, sample_time)
    joint_enabled = handles.payload_joint.GetJointEnabledAttr()
    joint_enabled.Set(attachment_enabled)
    joint_enabled.Set(attachment_enabled, sample_time)
    kinematic_enabled = handles.payload_body.GetKinematicEnabledAttr()
    if payload_dynamic_for_frame(frame) and not handles.payload_released:
        kinematic_enabled.Set(False)
        kinematic_enabled.Set(False, sample_time)
        handles.payload_released = True
    elif not handles.payload_released:
        kinematic_enabled.Set(True)
        kinematic_enabled.Set(True, sample_time)
    obstacle = UsdGeom.Imageable(handles.obstacle_root)
    obstacle.MakeVisible() if frame.obstacle_visible else obstacle.MakeInvisible()
    UsdGeom.Imageable(handles.beacon).GetPrim().GetAttribute("primvars:displayColor")


def observe_scene(handles: SceneHandles, *, base_speed_mps: float = 0.0) -> dict[str, object]:
    from pxr import Usd, UsdGeom

    time_code = Usd.TimeCode.Default()
    base = UsdGeom.Xformable(handles.forklift_root).ComputeLocalToWorldTransform(time_code).ExtractTranslation()
    lift = UsdGeom.Xformable(handles.lift_root).ComputeLocalToWorldTransform(time_code).ExtractTranslation()
    payload_transform = UsdGeom.Xformable(
        handles.payload_root
    ).ComputeLocalToWorldTransform(time_code)
    payload = payload_transform.ExtractTranslation()
    payload_rotation = payload_transform.ExtractRotationQuat()
    payload_yaw_deg = yaw_degrees_from_quaternion_components(
        payload_rotation.GetReal(),
        tuple(payload_rotation.GetImaginary()),
    )
    rotation = handles.fork_tilt_root.GetAttribute("xformOp:rotateXYZ").Get(time_code)
    base_rotation = handles.forklift_root.GetAttribute("xformOp:rotateXYZ").Get(time_code)
    visibility = UsdGeom.Imageable(handles.obstacle_root).ComputeVisibility(time_code)
    physical_attachment_enabled = bool(handles.payload_joint.GetJointEnabledAttr().Get(time_code))
    return derive_kinematic_observation(
        base=base,
        lift=lift,
        payload=payload,
        yaw_deg=float(base_rotation[2]),
        fork_tilt_deg=float(rotation[1]),
        obstacle_visible=visibility != UsdGeom.Tokens.invisible,
        base_speed_mps=base_speed_mps,
        physical_attachment_enabled=physical_attachment_enabled,
        payload_yaw_deg=payload_yaw_deg,
    )
