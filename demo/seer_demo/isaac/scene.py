"""Z-up OpenUSD warehouse scene for the deterministic Isaac demonstration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .timeline import FORKLIFT_PARTS, FrameState


def derive_kinematic_observation(
    *,
    base,
    lift,
    payload,
    fork_tilt_deg: float,
    obstacle_visible: bool,
    base_speed_mps: float,
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
    payload_attached = (
        abs(relative_payload[0] - 1.6) <= 0.03
        and abs(relative_payload[1]) <= 0.03
        and abs(relative_payload[2] - 0.25) <= 0.03
    )
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
    obstacle_root: Any
    beacon: Any


def build_scene(output_path: Path | str, scenario: str) -> SceneHandles:
    import omni.usd
    from pxr import Gf, UsdGeom, UsdLux

    context = omni.usd.get_context()
    context.new_stage()
    stage = context.get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = stage.DefinePrim("/World", "Xform")
    stage.SetDefaultPrim(world)

    def box(path, size, position, color, opacity=1.0):
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(1.0)
        common = UsdGeom.XformCommonAPI(cube)
        common.SetScale(Gf.Vec3f(*size))
        common.SetTranslate(Gf.Vec3d(*position))
        cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        if opacity < 1.0:
            cube.CreateDisplayOpacityAttr([opacity])
        return cube.GetPrim()

    # Warehouse floor, dock markings and backdrop.
    box("/World/Ground", (24.0, 16.0, 0.10), (0.0, 0.0, -0.05), (0.16, 0.19, 0.23))
    for x in range(-8, 9, 2):
        box(f"/World/Grid/X_{x+8}", (0.025, 14.0, 0.012), (float(x), 0.0, 0.012), (0.28, 0.32, 0.37))
    for y in range(-6, 7, 2):
        box(f"/World/Grid/Y_{y+6}", (20.0, 0.025, 0.012), (0.0, float(y), 0.012), (0.28, 0.32, 0.37))
    box("/World/Warehouse/BackWall", (20.0, 0.18, 4.5), (0.0, 6.5, 2.25), (0.25, 0.29, 0.34))
    box("/World/Warehouse/SideWall", (0.18, 13.0, 4.5), (9.5, 0.0, 2.25), (0.22, 0.26, 0.31))
    box("/World/Safety/ExitLaneLeft", (10.0, 0.07, 0.025), (-1.0, 1.55, 0.025), (0.95, 0.75, 0.06))
    box("/World/Safety/ExitLaneRight", (10.0, 0.07, 0.025), (-1.0, -1.55, 0.025), (0.95, 0.75, 0.06))

    # Open container uses Z as height; front is open at x=0.
    box("/World/Container/Floor", (6.0, 2.8, 0.12), (3.0, 0.0, 0.06), (0.31, 0.34, 0.37))
    box("/World/Container/Back", (0.12, 2.8, 3.0), (6.0, 0.0, 1.50), (0.46, 0.18, 0.12))
    box("/World/Container/Left", (6.0, 0.10, 3.0), (3.0, 1.40, 1.50), (0.55, 0.22, 0.14))
    # The camera-side wall and roof are transparent cutaways so pickup remains auditable on video.
    box(
        "/World/Container/Right",
        (6.0, 0.10, 3.0),
        (3.0, -1.40, 1.50),
        (0.55, 0.22, 0.14),
        opacity=0.18,
    )
    box(
        "/World/Container/Roof",
        (6.0, 2.8, 0.10),
        (3.0, 0.0, 3.0),
        (0.50, 0.20, 0.13),
        opacity=0.28,
    )
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
    for index, y in enumerate((-0.42, 0.0, 0.42)):
        box(f"/World/ActivePayload/Pallet/Slat{index}", (1.15, 0.24, 0.10), (0.0, y, 0.05), (0.48, 0.28, 0.10))
    for index, (x, y) in enumerate(((-0.28, -0.25), (-0.28, 0.25), (0.28, -0.25), (0.28, 0.25))):
        box(f"/World/ActivePayload/Cargo/Box{index}", (0.50, 0.42, 0.55), (x, y, 0.38), (0.72, 0.49, 0.22))

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

    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(650.0)
    key = UsdLux.RectLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(25000.0)
    key.CreateWidthAttr(8.0)
    key.CreateHeightAttr(5.0)
    UsdGeom.XformCommonAPI(key).SetTranslate(Gf.Vec3d(-1.0, -2.0, 8.0))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage.GetRootLayer().Export(str(output))
    return SceneHandles(
        stage,
        forklift_root,
        lift_root,
        fork_tilt_root,
        payload_root,
        obstacle_root,
        beacon,
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
    return derive_kinematic_observation(
        base=base,
        lift=lift,
        payload=payload,
        fork_tilt_deg=float(rotation[1]),
        obstacle_visible=visibility != UsdGeom.Tokens.invisible,
        base_speed_mps=base_speed_mps,
    )
