#!/usr/bin/env python3
"""Compose a raw Fast-WAM rollout with its frame-bound evidence panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "demo"))

from seer_demo.contracts import load_events  # noqa: E402
from seer_demo.fastwam.contracts import (  # noqa: E402
    load_action_records,
    validate_fastwam_package,
)
from seer_demo.fastwam.presentation import render_fastwam_frames  # noqa: E402
from seer_demo.manifest import assert_video_matches_summary, probe_video  # noqa: E402
from seer_demo.presentation import build_ffmpeg_command  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a 2560x1080 Fast-WAM split presentation")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--output", default="presentation.mp4")
    parser.add_argument("--keep-frames", action="store_true")
    return parser.parse_args()


def declared_file(run_dir: Path, value: object, label: str) -> Path:
    name = str(value or "")
    if not name or Path(name).name != name:
        raise ValueError(f"invalid {label} filename")
    path = run_dir / name
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    return path


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    events = load_events(declared_file(run_dir, summary.get("events_file"), "events"))
    actions = load_action_records(
        declared_file(run_dir, summary.get("actions_file"), "actions")
    )
    validate_fastwam_package(summary, events, actions)
    source_video = declared_file(run_dir, summary.get("video_file"), "source video")
    source_probe = probe_video(source_video)
    assert_video_matches_summary(summary, source_probe)
    fps = float(source_probe["fps"])
    frame_count = int(source_probe["frame_count"])
    output_name = str(args.output)
    if Path(output_name).name != output_name or output_name == source_video.name:
        raise ValueError("output must be a distinct basename")
    output_video = run_dir / output_name
    temporary_video = run_dir / f".{output_video.stem}.building.mp4"
    temporary_video.unlink(missing_ok=True)

    if args.keep_frames:
        frame_dir = run_dir / ".fastwam-presentation-frames"
        if frame_dir.exists():
            shutil.rmtree(frame_dir)
        overlay_pattern = render_fastwam_frames(
            events,
            actions,
            summary,
            frame_dir,
            frame_count=frame_count,
            font_path=args.font,
        )
        temporary = None
    else:
        temporary = tempfile.TemporaryDirectory(prefix="fastwam-presentation-")
        overlay_pattern = render_fastwam_frames(
            events,
            actions,
            summary,
            Path(temporary.name) / "frames",
            frame_count=frame_count,
            font_path=args.font,
        )
    try:
        command = build_ffmpeg_command(
            ffmpeg=args.ffmpeg,
            source_video=source_video,
            overlay_pattern=overlay_pattern,
            fps=fps,
            output_video=temporary_video,
        )
        subprocess.run(command, check=True)
        presentation_probe = probe_video(temporary_video)
        if (presentation_probe["width"], presentation_probe["height"]) != (2560, 1080):
            raise RuntimeError("presentation video has unexpected resolution")
        if presentation_probe["frame_count"] != frame_count:
            raise RuntimeError(
                f"presentation frame count changed: {presentation_probe['frame_count']} != {frame_count}"
            )
        if abs(float(presentation_probe["fps"]) - fps) > 1e-6:
            raise RuntimeError("presentation fps changed")
        temporary_video.replace(output_video)
        summary.update(
            {
                "presentation_file": output_video.name,
                "presentation_resolution": "2560x1080",
                "presentation_fps": fps,
                "presentation_frame_count": frame_count,
                "presentation_duration_s": presentation_probe["duration_s"],
                "presentation_contract": "auditable_common_projection_v2",
            }
        )
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({"output": str(output_video), "probe": presentation_probe}, indent=2))
    finally:
        temporary_video.unlink(missing_ok=True)
        if temporary is not None:
            temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
