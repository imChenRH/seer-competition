"""Pure-Python trajectory truth shared by tests and the Isaac recorder."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping

from ..scenarios import get_scenario


@dataclass(frozen=True, slots=True)
class PartSpec:
    size: tuple[float, float, float]
    local_position: tuple[float, float, float]
    color: tuple[float, float, float]


FORKLIFT_PARTS: Mapping[str, PartSpec] = {
    "chassis": PartSpec((2.2, 1.15, 0.55), (0.0, 0.0, 0.48), (0.94, 0.55, 0.08)),
    "counterweight": PartSpec((0.75, 1.05, 0.85), (-0.70, 0.0, 0.95), (0.90, 0.43, 0.04)),
    "cabin": PartSpec((0.85, 0.95, 1.25), (-0.10, 0.0, 1.25), (0.18, 0.25, 0.30)),
    "mast_left": PartSpec((0.13, 0.13, 2.50), (1.05, 0.42, 1.40), (0.16, 0.18, 0.21)),
    "mast_right": PartSpec((0.13, 0.13, 2.50), (1.05, -0.42, 1.40), (0.16, 0.18, 0.21)),
    "overhead_guard": PartSpec((1.05, 1.05, 0.10), (-0.10, 0.0, 2.05), (0.12, 0.14, 0.17)),
    "wheel_fl": PartSpec((0.42, 0.24, 0.42), (0.72, 0.63, 0.42), (0.04, 0.04, 0.05)),
    "wheel_fr": PartSpec((0.42, 0.24, 0.42), (0.72, -0.63, 0.42), (0.04, 0.04, 0.05)),
    "wheel_rl": PartSpec((0.48, 0.24, 0.48), (-0.72, 0.63, 0.44), (0.04, 0.04, 0.05)),
    "wheel_rr": PartSpec((0.48, 0.24, 0.48), (-0.72, -0.63, 0.44), (0.04, 0.04, 0.05)),
}


@dataclass(frozen=True, slots=True)
class FrameState:
    frame: int
    sim_time_s: float
    scenario: str
    phase: str
    skill_id: str | None
    fallback_id: str | None
    attempt: int
    base_x_m: float
    base_y_m: float
    base_z_m: float
    yaw_deg: float
    mast_height_m: float
    fork_tilt_deg: float
    payload_x_m: float
    payload_y_m: float
    payload_z_m: float
    payload_attached: bool
    payload_placed: bool
    pallet_lateral_error_m: float
    obstacle_visible: bool
    stopped: bool
    outcome: str

    def to_observed_state(self) -> dict[str, object]:
        return {
            "base_x_m": self.base_x_m,
            "base_y_m": self.base_y_m,
            "base_z_m": self.base_z_m,
            "yaw_deg": self.yaw_deg,
            "mast_height_m": self.mast_height_m,
            "fork_tilt_deg": self.fork_tilt_deg,
            "payload_x_m": self.payload_x_m,
            "payload_y_m": self.payload_y_m,
            "payload_z_m": self.payload_z_m,
            "payload_attached": self.payload_attached,
            "payload_placed": self.payload_placed,
            "pallet_lateral_error_m": self.pallet_lateral_error_m,
            "obstacle_visible": self.obstacle_visible,
            "stopped": self.stopped,
        }


@dataclass(frozen=True, slots=True)
class Timeline:
    scenario: str
    fps: int
    duration_s: float
    frames: tuple[FrameState, ...]


@dataclass(frozen=True, slots=True)
class _Pose:
    base_x_m: float = -6.0
    base_y_m: float = 0.0
    mast_height_m: float = 0.22
    fork_tilt_deg: float = 0.0
    payload_attached: bool = False
    payload_placed: bool = False
    pallet_lateral_error_m: float = 0.0
    stopped: bool = False


@dataclass(frozen=True, slots=True)
class _Segment:
    phase: str
    duration_s: float
    skill_id: str | None = None
    fallback_id: str | None = None
    attempt: int = 1
    base_x_m: float | None = None
    base_y_m: float | None = None
    mast_height_m: float | None = None
    fork_tilt_deg: float | None = None
    pallet_lateral_error_m: float | None = None
    attach_at_end: bool = False
    release_at_end: bool = False
    stop_at_end: bool = False


def _segments(scenario: str) -> tuple[_Segment, ...]:
    common_start = (
        _Segment("enter_container", 10, skill_id="FORK-NAV-01", base_x_m=0.5),
        _Segment("precision_approach", 8, skill_id="FORK-NAV-03", base_x_m=2.2),
    )
    if scenario == "intervention":
        return common_start + (
            _Segment("occluded_view_1", 3, skill_id="FORK-PER-01", attempt=1),
            _Segment("view_adjust_1", 2, fallback_id="FB-F02", attempt=1, base_y_m=0.15),
            _Segment("occluded_view_2", 3, skill_id="FORK-PER-01", attempt=2),
            _Segment("view_adjust_2", 2, fallback_id="FB-F02", attempt=2, base_y_m=-0.15),
            _Segment("occluded_view_3", 3, skill_id="FORK-PER-01", attempt=3),
            _Segment("safe_retreat", 4, fallback_id="FB-F07", base_x_m=-1.0, base_y_m=0.0),
            _Segment("safety_stop", 1, fallback_id="FB-F07", stop_at_end=True),
        )
    if scenario == "recovery":
        perception = (
            _Segment(
                "offset_detected",
                3,
                skill_id="FORK-PER-01",
                attempt=1,
                pallet_lateral_error_m=0.25,
            ),
            _Segment(
                "lateral_realign",
                8,
                fallback_id="FB-F01",
                base_y_m=0.25,
                pallet_lateral_error_m=0.0,
            ),
            _Segment("pose_revalidated", 3, skill_id="FORK-PER-01", attempt=2),
        )
    else:
        perception = (_Segment("pose_verified", 3, skill_id="FORK-PER-01"),)
    common_finish = (
        _Segment("insert_forks", 4, skill_id="FORK-OP-01", base_x_m=2.25, attach_at_end=True),
        _Segment("lift_payload", 3, skill_id="FORK-OP-02", mast_height_m=1.05),
        _Segment("tilt_stabilize", 2, skill_id="FORK-OP-03", fork_tilt_deg=4.0),
        _Segment("exit_container", 10, skill_id="FORK-NAV-02", base_x_m=-1.0),
        _Segment("align_conveyor", 6, skill_id="FORK-OP-05", base_x_m=-5.0, base_y_m=-2.0),
        _Segment(
            "place_payload",
            5,
            skill_id="FORK-OP-04",
            mast_height_m=0.35,
            fork_tilt_deg=0.0,
            release_at_end=True,
        ),
    )
    return common_start + perception + common_finish


def _smooth(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def _interpolate(start: float, end: float, amount: float) -> float:
    return start + (end - start) * _smooth(amount)


def build_timeline(scenario: str, fps: int = 8) -> Timeline:
    get_scenario(scenario)
    if not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps must be a positive integer")
    initial_error = 0.25 if scenario == "recovery" else 0.0
    pose = _Pose(pallet_lateral_error_m=initial_error)
    obstacle_visible = scenario == "intervention"
    pickup_y = 0.25 if scenario == "recovery" else 0.0
    frames: list[FrameState] = []
    elapsed = 0.0

    def append_frame(current: _Pose, segment: _Segment, amount: float, final_outcome: str = "RUNNING"):
        attached = current.payload_attached
        placed = current.payload_placed
        base_x = round(current.base_x_m, 6)
        base_y = round(current.base_y_m, 6)
        mast_height = round(current.mast_height_m, 6)
        if attached:
            payload_x = base_x + 1.6
            payload_y = base_y
            payload_z = mast_height + 0.25
        elif placed:
            payload_x, payload_y, payload_z = -3.4, -2.0, 0.55
        else:
            payload_x, payload_y, payload_z = 3.85, pickup_y, 0.32
        frames.append(
            FrameState(
                frame=len(frames),
                sim_time_s=round(elapsed + amount * segment.duration_s, 6),
                scenario=scenario,
                phase=segment.phase,
                skill_id=segment.skill_id,
                fallback_id=segment.fallback_id,
                attempt=segment.attempt,
                base_x_m=base_x,
                base_y_m=base_y,
                base_z_m=0.0,
                yaw_deg=0.0,
                mast_height_m=mast_height,
                fork_tilt_deg=round(current.fork_tilt_deg, 6),
                payload_x_m=round(payload_x, 6),
                payload_y_m=round(payload_y, 6),
                payload_z_m=round(payload_z, 6),
                payload_attached=attached,
                payload_placed=placed,
                pallet_lateral_error_m=round(current.pallet_lateral_error_m, 6),
                obstacle_visible=obstacle_visible,
                stopped=current.stopped,
                outcome=final_outcome,
            )
        )

    segments = _segments(scenario)
    append_frame(pose, segments[0], 0.0)
    for segment_index, segment in enumerate(segments):
        start = pose
        target = replace(
            start,
            base_x_m=start.base_x_m if segment.base_x_m is None else segment.base_x_m,
            base_y_m=start.base_y_m if segment.base_y_m is None else segment.base_y_m,
            mast_height_m=(
                start.mast_height_m if segment.mast_height_m is None else segment.mast_height_m
            ),
            fork_tilt_deg=(
                start.fork_tilt_deg if segment.fork_tilt_deg is None else segment.fork_tilt_deg
            ),
            pallet_lateral_error_m=(
                start.pallet_lateral_error_m
                if segment.pallet_lateral_error_m is None
                else segment.pallet_lateral_error_m
            ),
        )
        steps = int(round(segment.duration_s * fps))
        for step in range(1, steps + 1):
            amount = step / steps
            current = replace(
                start,
                base_x_m=_interpolate(start.base_x_m, target.base_x_m, amount),
                base_y_m=_interpolate(start.base_y_m, target.base_y_m, amount),
                mast_height_m=_interpolate(start.mast_height_m, target.mast_height_m, amount),
                fork_tilt_deg=_interpolate(start.fork_tilt_deg, target.fork_tilt_deg, amount),
                pallet_lateral_error_m=_interpolate(
                    start.pallet_lateral_error_m, target.pallet_lateral_error_m, amount
                ),
            )
            if step == steps and segment.attach_at_end:
                current = replace(current, payload_attached=True)
            if step == steps and segment.release_at_end:
                current = replace(current, payload_attached=False, payload_placed=True)
            if step == steps and segment.stop_at_end:
                current = replace(current, stopped=True)
            is_final = segment_index == len(segments) - 1 and step == steps
            outcome = (
                "HUMAN_REQUIRED" if scenario == "intervention" else "COMPLETED"
            ) if is_final else "RUNNING"
            append_frame(current, segment, amount, outcome)
        pose = current
        elapsed += segment.duration_s
    return Timeline(scenario=scenario, fps=fps, duration_s=elapsed, frames=tuple(frames))
