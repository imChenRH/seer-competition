"""Headless Isaac Sim runner that records frames and observed JSONL evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Mapping

from ..contracts import EventWriter, load_events, validate_scenario_events
from ..engine import ActionResult, DemoEngine
from ..scenarios import (
    SCENARIOS,
    SKILL_DURATIONS_S,
    fallback_state_succeeded,
    skill_state_succeeded,
)
from .timeline import Timeline, build_timeline


class IsaacTimelineBackend:
    def __init__(self, timeline: Timeline, observations: Mapping[tuple[str, str, int], Mapping[str, object]]):
        self.timeline = timeline
        self.observations = observations
        self._state = timeline.frames[0].to_observed_state()
        self._observed_frame = timeline.frames[0].frame

    def snapshot(self):
        return dict(self._state)

    def snapshot_evidence(self):
        return {
            "backend": "isaac_sim",
            "stage_observed": True,
            "observed_frame": self._observed_frame,
        }

    def execute_skill(self, skill_id: str, attempt: int) -> ActionResult:
        state, frame = self._observed("skill", skill_id, attempt)
        success = skill_state_succeeded(skill_id, state)
        confidence = 0.93 if success else max(0.20, 0.45 - attempt * 0.04)
        return ActionResult(
            success=success,
            duration_s=SKILL_DURATIONS_S[skill_id],
            state=state,
            evidence={
                "backend": "isaac_sim",
                "stage_observed": True,
                "observed_frame": frame,
                "confidence": confidence,
            },
            message=f"{skill_id} {'状态验证通过' if success else '观测未通过阈值'}",
        )

    def execute_fallback(self, fallback_id: str, attempt: int) -> ActionResult:
        state, frame = self._observed("fallback", fallback_id, attempt)
        durations = {"FB-F01": 8.0, "FB-F02": 2.0, "FB-F07": 4.0}
        success = fallback_state_succeeded(fallback_id, state)
        return ActionResult(
            success=success,
            duration_s=durations[fallback_id],
            state=state,
            evidence={"backend": "isaac_sim", "stage_observed": True, "observed_frame": frame},
            message={
                "FB-F01": "Isaac 场景内横向重对位完成",
                "FB-F02": "Isaac 场景内观察位姿调整完成",
                "FB-F07": "Isaac 场景内退回安全等待点",
            }[fallback_id],
        )

    def safety_stop(self) -> ActionResult:
        state, frame = self._observed("safety", "FB-F07", 1)
        return ActionResult(
            success=(
                state.get("stopped") is True
                and abs(float(state.get("base_speed_mps", 999.0))) <= 0.01
            ),
            duration_s=1.0,
            state=state,
            evidence={
                "backend": "isaac_sim",
                "stage_observed": True,
                "observed_frame": frame,
                "velocity_verified_mps": state.get("base_speed_mps"),
            },
            message="Isaac 场景内车辆停稳",
        )

    def _observed(self, kind: str, identifier: str, attempt: int):
        key = (kind, identifier, attempt)
        if key not in self.observations:
            raise RuntimeError(f"missing stage observation for {key}")
        record = dict(self.observations[key])
        frame = int(record.pop("_frame"))
        self._state = record
        self._observed_frame = frame
        return dict(record), frame



def _parse_resolution(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("resolution must look like 1280x720") from exc
    if width < 640 or height < 360:
        raise argparse.ArgumentTypeError("resolution must be at least 640x360")
    return width, height


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a truthful SEER Isaac Sim scenario")
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--fps", type=int, default=8)
    parser.add_argument("--resolution", type=_parse_resolution, default=(1280, 720))
    return parser


def _encode_video(frames_dir: Path, output_path: Path, fps: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to encode the Isaac recording")
    process = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%05d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
    )
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {process.stderr[-1000:]}")


def run_isaac(args: argparse.Namespace) -> dict[str, object]:
    if args.fps <= 0:
        raise ValueError("fps must be positive")
    os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    from isaacsim import SimulationApp

    width, height = args.resolution
    app = SimulationApp({"headless": True, "width": width, "height": height})
    try:
        import omni.replicator.core as rep
        import omni.timeline
        from omni.replicator.core.functional import write_image

        from .scene import apply_frame, build_scene, observe_scene

        output_dir: Path = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        timeline = build_timeline(args.scenario, fps=args.fps)
        handles = build_scene(output_dir / "scene.usda", args.scenario)
        omni.timeline.get_timeline_interface().play()
        for _ in range(60):
            app.update()

        camera = rep.functional.create.camera(
            position=(-11.5, -14.0, 10.5),
            look_at=(-0.5, -0.2, 0.9),
            parent="/World",
            name="DemoCamera",
        )
        render_product = rep.create.render_product(camera, resolution=(width, height), name="DemoRender")
        rgb = rep.annotators.get("rgb")
        rgb.attach(render_product)
        observations: dict[tuple[str, str, int], dict[str, object]] = {}
        previous_base: tuple[float, float] | None = None
        previous_time: float | None = None
        for index, frame in enumerate(timeline.frames):
            apply_frame(handles, frame)
            rep.orchestrator.step(rt_subframes=2)
            write_image(path=str(frames_dir / f"frame_{index:05d}.png"), data=rgb.get_data())
            observed = observe_scene(handles, base_speed_mps=0.0)
            if previous_base is None or previous_time is None:
                base_speed_mps = 0.0
            else:
                delta_time = frame.sim_time_s - previous_time
                delta_x = float(observed["base_x_m"]) - previous_base[0]
                delta_y = float(observed["base_y_m"]) - previous_base[1]
                base_speed_mps = (
                    (delta_x * delta_x + delta_y * delta_y) ** 0.5 / delta_time
                    if delta_time > 0
                    else 0.0
                )
            observed["base_speed_mps"] = round(base_speed_mps, 6)
            observed["stopped"] = base_speed_mps <= 0.01
            observed["safe_retreat_complete"] = (
                float(observed["base_x_m"]) <= -0.9
                and observed["payload_attached"] is False
            )
            previous_base = (
                float(observed["base_x_m"]),
                float(observed["base_y_m"]),
            )
            previous_time = frame.sim_time_s
            next_frame = timeline.frames[index + 1] if index + 1 < len(timeline.frames) else None
            if next_frame is None or next_frame.phase != frame.phase:
                observed["_frame"] = frame.frame
                if frame.phase == "safety_stop":
                    key = ("safety", "FB-F07", 1)
                elif frame.skill_id:
                    key = ("skill", frame.skill_id, frame.attempt)
                elif frame.fallback_id:
                    key = ("fallback", frame.fallback_id, frame.attempt)
                else:
                    continue
                observations[key] = observed

        handles.stage.GetRootLayer().Export(str(output_dir / "scene.usda"))

        video_path = output_dir / "simulation.mp4"
        _encode_video(frames_dir, video_path, args.fps)
        events_path = output_dir / "events.jsonl"
        with EventWriter(events_path, args.run_id, args.scenario, "isaac_sim") as writer:
            DemoEngine(IsaacTimelineBackend(timeline, observations), writer).run(args.scenario)
        validation = validate_scenario_events(
            load_events(events_path), expected_scenario=args.scenario
        )
        summary = asdict(validation)
        summary.update(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "controller": "deterministic_kinematic_rule_controller",
                "isaac_version": "6.0.1",
                "frame_count": len(timeline.frames),
                "fps": args.fps,
                "resolution": f"{width}x{height}",
                "events_file": "events.jsonl",
                "video_file": "simulation.mp4",
                "scene_file": "scene.usda",
            }
        )
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        print(
            f"ISAAC_RUN_FAILED:{type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        app.close(exit_code=2)
        raise
    else:
        print("ISAAC_RUN_COMPLETE:" + json.dumps(summary, ensure_ascii=False), flush=True)
        app.close(exit_code=0)
        return summary


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = run_isaac(args)
    except Exception as exc:
        print(f"ISAAC_RUN_FAILED:{type(exc).__name__}:{exc}", file=sys.stderr, flush=True)
        return 2
    # In normal Isaac fast-shutdown mode run_isaac exits from app.close().
    # This return remains useful for tests or hosts that disable fast shutdown.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
