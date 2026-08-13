"""Z-up OpenUSD warehouse scene for the deterministic Isaac demonstration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .timeline import FORKLIFT_PARTS, FrameState


WAREHOUSE_EXTENT_M = (44.0, 28.0)
PHYSICS_SCHEMA_APIS = (
    "PhysicsScene",
    "CollisionAPI",
    "RigidBodyAPI",
    "MassAPI",
    "ArticulationRootAPI",
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


@dataclass(frozen=True, slots=True)
class PalletPartSpec:
    role: str
    size: tuple[float, float, float]
    position: tuple[float, float, float]
    color: tuple[float, float, float]


def pallet_part_specs() -> tuple[PalletPartSpec, ...]:
    """Build a pallet with two unobstructed, fork-aligned entry pockets."""
    wood = (0.48, 0.28, 0.10)
    parts: list[PalletPartSpec] = []
    for index, y in enumerate((-0.52, -0.26, 0.0, 0.26, 0.52)):
        parts.append(PalletPartSpec("deck", (1.15, 0.18, 0.09), (0.0, y, 0.16), wood))
    for y in (-0.58, 0.0, 0.58):
        parts.append(PalletPartSpec("runner", (1.15, 0.12, 0.10), (0.0, y, 0.05), wood))
    return tuple(parts)


def physical_attachment_for_frame(frame: FrameState) -> bool:
    """Return the authored FixedJoint state for one evidence frame."""
    return bool(frame.payload_attached)


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
        return CameraPose((-3.8, -5.0, 5.4), (2.7, 0.0, 0.8))
    if phase in {"insert_forks", "lift_payload", "tilt_stabilize"}:
        return CameraPose((-2.8, -5.2, 4.0), (2.6, 0.0, 0.85))
    if phase in {"align_conveyor", "place_payload"}:
        return CameraPose((-10.5, -5.2, 4.8), (-3.4, -2.0, 0.75))
    if phase in {"safe_retreat", "safety_stop"}:
        return CameraPose((-9.5, -5.4, 6.2), (-0.5, 0.0, 0.9))
    return CameraPose((-16.5, -5.6, 6.2), (-0.5, 0.0, 0.9))


def derive_kinematic_observation(
    *,
    base,
    lift,
    payload,
    fork_tilt_deg: float,
    obstacle_visible: bool,
    base_speed_mps: float,
    physical_attachment_enabled: bool,
) -> dict[str, object]:
    """Derive state from measured transforms/visibility, never scenario labels."""
    base_xyz = tuple(float(value) for value in base)
    lift_xyz = tuple(float(value) for value in lift)
    payload_xyz = tuple(float(value) for value in payload)
    mast_height = lift_xyz[2] - base_xyz[2]
    relative_payload = (
        payload_xyz[0] - base_xyz[0],
        payload_xyz[1] - base_xyz[1],
        payload_xyz[2] - base_xyz[2] - mast_height,
    )
    geometry_attached = (
        abs(relative_payload[0] - 1.6) <= 0.03
        and abs(relative_payload[1]) <= 0.03
        and abs(relative_payload[2] - 0.25) <= 0.03
    )
    payload_attached = geometry_attached and bool(physical_attachment_enabled)
    payload_placed = (
        not payload_attached
        and abs(payload_xyz[0] + 3.4) <= 0.03
        and abs(payload_xyz[1] + 2.0) <= 0.03
        and abs(payload_xyz[2] - 0.55) <= 0.03
    )
    stopped = abs(float(base_speed_mps)) <= 0.01
    pallet_error = 0.0 if payload_attached else payload_xyz[1] - base_xyz[1]
    return {
        "base_x_m": round(base_xyz[0], 6),
        "base_y_m": round(base_xyz[1], 6),
        "base_z_m": round(base_xyz[2], 6),
        "base_speed_mps": round(float(base_speed_mps), 6),
        "mast_height_m": round(mast_height, 6),
        "fork_tilt_deg": round(float(fork_tilt_deg), 6),
        "payload_x_m": round(payload_xyz[0], 6),
        "payload_y_m": round(payload_xyz[1], 6),
        "payload_z_m": round(payload_xyz[2], 6),
        "payload_attached": payload_attached,
        "physical_attachment_enabled": bool(physical_attachment_enabled),
        "payload_placed": payload_placed,
        "pallet_lateral_error_m": round(pallet_error, 6),
        "obstacle_visible": bool(obstacle_visible),
        "stopped": stopped,
        "safe_retreat_complete": (
            base_xyz[0] <= -0.9 and not payload_attached
        ),
        "aligned_with_conveyor": (
            base_xyz[0] <= -4.9 and base_xyz[1] <= -1.9
        ),
    }


@dataclass(slots=True)
class SceneHandles:
    stage: Any
    forklift_root: Any
    lift_root: Any
    fork_tilt_root: Any
    payload_root: Any
    payload_joint: Any
    obstacle_root: Any
    beacon: Any
    referenced_assets: tuple[str, ...]


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

    # Expanded warehouse floor, aisle markings and shell.
    width, depth = WAREHOUSE_EXTENT_M
    box("/World/Ground", (width, depth, 0.10), (0.0, 0.0, -0.05), (0.16, 0.19, 0.23), material_name="Concrete")
    for x in range(-20, 21, 2):
        box(f"/World/Grid/X_{x+20}", (0.018, depth - 1.0, 0.012), (float(x), 0.0, 0.012), (0.28, 0.32, 0.37), collision=False)
    for y in range(-12, 13, 2):
        box(f"/World/Grid/Y_{y+12}", (width - 2.0, 0.018, 0.012), (0.0, float(y), 0.012), (0.28, 0.32, 0.37), collision=False)
    box("/World/Warehouse/BackWall", (width - 1.0, 0.22, 7.5), (0.0, depth / 2 - 0.5, 3.75), (0.19, 0.23, 0.27), material_name="WarehouseSteel")
    box("/World/Warehouse/SideWall", (0.22, depth - 1.0, 7.5), (width / 2 - 0.5, 0.0, 3.75), (0.18, 0.22, 0.26), material_name="WarehouseSteel")
    for index, x in enumerate(range(-18, 19, 6)):
        box(f"/World/Warehouse/CeilingBeam{index}", (0.18, depth - 1.0, 0.26), (float(x), 0.0, 7.0), (0.12, 0.15, 0.18), material_name="WarehouseSteel")
    for index, y in enumerate((-3.3, 3.3)):
        box(f"/World/Safety/MainLane{index}", (width - 5.0, 0.08, 0.025), (0.0, y, 0.025), (0.95, 0.75, 0.06), material_name="SafetyYellow")
    box("/World/Safety/ExitLaneLeft", (10.0, 0.07, 0.025), (-1.0, 1.55, 0.025), (0.95, 0.75, 0.06))
    box("/World/Safety/ExitLaneRight", (10.0, 0.07, 0.025), (-1.0, -1.55, 0.025), (0.95, 0.75, 0.06))

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

    # Open container uses Z as height; front is open at x=0.
    box("/World/Container/Floor", (6.0, 2.8, 0.12), (3.0, 0.0, 0.06), (0.31, 0.34, 0.37))
    box("/World/Container/Back", (0.12, 2.8, 3.0), (6.0, 0.0, 1.50), (0.46, 0.18, 0.12))
    box("/World/Container/Left", (6.0, 0.10, 3.0), (3.0, 1.40, 1.50), (0.55, 0.22, 0.14))
    # Camera-side panels are structural cutaways; rails preserve the container silhouette
    # without hiding fork insertion and payload contact from the evidence camera.
    box("/World/Container/RightTopRail", (6.0, 0.10, 0.12), (3.0, -1.40, 2.94), (0.55, 0.22, 0.14))
    box("/World/Container/RoofBackRail", (0.12, 2.8, 0.12), (5.94, 0.0, 2.94), (0.50, 0.20, 0.13))
    for index, y in enumerate((-1.22, 1.22)):
        box(f"/World/Container/DoorFrame{index}", (0.12, 0.12, 3.0), (0.0, y, 1.50), (0.75, 0.33, 0.16))

    # Conveyor target is offset from the inbound lane so the complete route stays visible.
    box("/World/Conveyor/Base", (3.2, 1.35, 0.62), (-3.4, -2.0, 0.31), (0.12, 0.25, 0.38))
    for index in range(9):
        box(
            f"/World/Conveyor/Roller{index}",
            (0.16, 1.15, 0.16),
            (-4.65 + index * 0.31, -2.0, 0.70),
            (0.52, 0.58, 0.63),
        )
    box("/World/Conveyor/Target", (1.4, 1.15, 0.025), (-3.4, -2.0, 0.80), (0.10, 0.65, 0.42))

    # Forklift is one root with local child geometry. Lift is the only moving child group.
    forklift_root = stage.DefinePrim("/World/Forklift", "Xform")
    forklift_body = UsdPhysics.RigidBodyAPI.Apply(forklift_root)
    forklift_body.CreateKinematicEnabledAttr(True)
    UsdPhysics.MassAPI.Apply(forklift_root).CreateMassAttr(3200.0)
    UsdPhysics.ArticulationRootAPI.Apply(forklift_root)
    stage.DefinePrim("/World/Forklift/Body", "Xform")
    for name, spec in FORKLIFT_PARTS.items():
        box(f"/World/Forklift/Body/{name}", spec.size, spec.local_position, spec.color)
    lift_root = stage.DefinePrim("/World/Forklift/Lift", "Xform")
    fork_tilt_root = stage.DefinePrim("/World/Forklift/Lift/ForkTilt", "Xform")
    box("/World/Forklift/Lift/ForkTilt/Carrier", (0.18, 0.92, 0.40), (1.12, 0.0, 0.25), (0.25, 0.29, 0.34))
    box("/World/Forklift/Lift/ForkTilt/ForkLeft", (1.35, 0.13, 0.10), (1.70, 0.32, 0.08), (0.13, 0.15, 0.18))
    box("/World/Forklift/Lift/ForkTilt/ForkRight", (1.35, 0.13, 0.10), (1.70, -0.32, 0.08), (0.13, 0.15, 0.18))
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
    for index, (x, y) in enumerate(((-0.28, -0.25), (-0.28, 0.25), (0.28, -0.25), (0.28, 0.25))):
        box(f"/World/ActivePayload/Cargo/Box{index}", (0.50, 0.42, 0.55), (x, y, 0.38), (0.72, 0.49, 0.22))

    payload_joint = UsdPhysics.FixedJoint.Define(stage, "/World/Constraints/PayloadAttachment")
    payload_joint.CreateBody0Rel().SetTargets([Sdf.Path("/World/Forklift")])
    payload_joint.CreateBody1Rel().SetTargets([Sdf.Path("/World/ActivePayload")])
    payload_joint.CreateJointEnabledAttr(False)

    # Background pallets show the container is a multi-load task, not an isolated cube.
    for row, (x, y) in enumerate(((4.9, 0.82), (4.9, -0.82))):
        box(f"/World/BackgroundLoads/Load{row}/Pallet", (1.0, 0.75, 0.12), (x, y, 0.12), (0.42, 0.24, 0.09))
        box(f"/World/BackgroundLoads/Load{row}/Cargo", (0.80, 0.60, 0.75), (x, y, 0.55), (0.35, 0.55, 0.72))

    obstacle_root = stage.DefinePrim("/World/Obstacle", "Xform")
    box("/World/Obstacle/FallenBoxA", (0.85, 0.70, 0.85), (0.0, 0.0, 0.43), (0.78, 0.16, 0.12))
    box("/World/Obstacle/FallenBoxB", (0.65, 0.65, 0.65), (0.35, 0.30, 0.32), (0.92, 0.42, 0.08))
    UsdGeom.XformCommonAPI(obstacle_root).SetTranslate(Gf.Vec3d(3.15, 0.0, 0.0))
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
        stage,
        forklift_root,
        lift_root,
        fork_tilt_root,
        payload_root,
        payload_joint,
        obstacle_root,
        beacon,
        tuple(referenced_assets),
    )


def apply_frame(handles: SceneHandles, frame: FrameState) -> None:
    from pxr import Gf, Usd, UsdGeom

    base_value = Gf.Vec3d(frame.base_x_m, frame.base_y_m, frame.base_z_m)
    lift_value = Gf.Vec3d(0.0, 0.0, frame.mast_height_m)
    tilt_value = Gf.Vec3f(0.0, frame.fork_tilt_deg, 0.0)
    payload_value = Gf.Vec3d(frame.payload_x_m, frame.payload_y_m, frame.payload_z_m)
    base_api = UsdGeom.XformCommonAPI(handles.forklift_root)
    lift_api = UsdGeom.XformCommonAPI(handles.lift_root)
    tilt_api = UsdGeom.XformCommonAPI(handles.fork_tilt_root)
    payload_api = UsdGeom.XformCommonAPI(handles.payload_root)
    base_api.SetTranslate(base_value)
    lift_api.SetTranslate(lift_value)
    tilt_api.SetRotate(
        tilt_value,
        UsdGeom.XformCommonAPI.RotationOrderXYZ,
    )
    payload_api.SetTranslate(payload_value)
    sample_time = Usd.TimeCode(frame.sim_time_s)
    handles.forklift_root.GetAttribute("xformOp:translate").Set(base_value, sample_time)
    handles.lift_root.GetAttribute("xformOp:translate").Set(lift_value, sample_time)
    handles.fork_tilt_root.GetAttribute("xformOp:rotateXYZ").Set(tilt_value, sample_time)
    handles.payload_root.GetAttribute("xformOp:translate").Set(payload_value, sample_time)
    attachment_enabled = physical_attachment_for_frame(frame)
    joint_enabled = handles.payload_joint.GetJointEnabledAttr()
    joint_enabled.Set(attachment_enabled)
    joint_enabled.Set(attachment_enabled, sample_time)
    obstacle = UsdGeom.Imageable(handles.obstacle_root)
    obstacle.MakeVisible() if frame.obstacle_visible else obstacle.MakeInvisible()
    UsdGeom.Imageable(handles.beacon).GetPrim().GetAttribute("primvars:displayColor")


def observe_scene(handles: SceneHandles, *, base_speed_mps: float = 0.0) -> dict[str, object]:
    from pxr import Usd, UsdGeom

    time_code = Usd.TimeCode.Default()
    base = UsdGeom.Xformable(handles.forklift_root).ComputeLocalToWorldTransform(time_code).ExtractTranslation()
    lift = UsdGeom.Xformable(handles.lift_root).ComputeLocalToWorldTransform(time_code).ExtractTranslation()
    payload = UsdGeom.Xformable(handles.payload_root).ComputeLocalToWorldTransform(time_code).ExtractTranslation()
    rotation = handles.fork_tilt_root.GetAttribute("xformOp:rotateXYZ").Get(time_code)
    visibility = UsdGeom.Imageable(handles.obstacle_root).ComputeVisibility(time_code)
    physical_attachment_enabled = bool(handles.payload_joint.GetJointEnabledAttr().Get(time_code))
    return derive_kinematic_observation(
        base=base,
        lift=lift,
        payload=payload,
        fork_tilt_deg=float(rotation[1]),
        obstacle_visible=visibility != UsdGeom.Tokens.invisible,
        base_speed_mps=base_speed_mps,
        physical_attachment_enabled=physical_attachment_enabled,
    )
