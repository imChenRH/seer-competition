"""Build a machine-verifiable manifest for recorded evidence runs."""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Mapping

from .contracts import load_events, validate_scenario_events


AUXILIARY_EVIDENCE_FILES = (
    "FEISHU_LIVE_RECEIPT.json",
    "fastwam/README.md",
    "fastwam/validation.log",
)


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_video(path: Path) -> dict[str, object]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required to build the evidence manifest")
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_frames,duration",
            "-of",
            "json",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    if process.returncode != 0:
        raise ValueError(f"ffprobe failed for {path.name}: {process.stderr[-500:]}")
    document = json.loads(process.stdout)
    streams = document.get("streams", [])
    if len(streams) != 1:
        raise ValueError(f"expected one video stream in {path}")
    stream = streams[0]
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": float(Fraction(stream["r_frame_rate"])),
        "frame_count": int(stream["nb_read_frames"]),
        "duration_s": float(stream["duration"]),
    }


def _safe_declared_file(run_dir: Path, value: object, label: str) -> Path:
    name = str(value or "")
    if not name or Path(name).name != name:
        raise ValueError(f"invalid {label} filename in {run_dir / 'summary.json'}")
    path = run_dir / name
    if not path.is_file():
        raise ValueError(f"missing declared {label} file: {path}")
    return path


def _assert_summary(summary: Mapping[str, object], validation) -> None:
    for key in ("run_id", "scenario", "source", "event_count", "terminal_status", "duration_s"):
        actual = getattr(validation, key)
        if summary.get(key) != actual:
            raise ValueError(f"summary {key} disagrees with validated events")


def _assert_video(summary: Mapping[str, object], video: Mapping[str, object]) -> None:
    if "resolution" in summary:
        expected_width, expected_height = (int(value) for value in str(summary["resolution"]).split("x"))
        if (video.get("width"), video.get("height")) != (expected_width, expected_height):
            raise ValueError("video resolution disagrees with summary")
    if "fps" in summary and abs(float(video.get("fps", -1)) - float(summary["fps"])) > 1e-6:
        raise ValueError("video fps disagrees with summary")
    if "frame_count" in summary and video.get("frame_count") != summary["frame_count"]:
        raise ValueError("video frame_count disagrees with summary")


def _assert_presentation(summary: Mapping[str, object], video: Mapping[str, object]) -> None:
    if "presentation_resolution" in summary:
        expected_width, expected_height = (
            int(value) for value in str(summary["presentation_resolution"]).split("x")
        )
        if (video.get("width"), video.get("height")) != (expected_width, expected_height):
            raise ValueError("presentation resolution disagrees with summary")
    if "presentation_fps" in summary and abs(
        float(video.get("fps", -1)) - float(summary["presentation_fps"])
    ) > 1e-6:
        raise ValueError("presentation fps disagrees with summary")
    if (
        "presentation_frame_count" in summary
        and video.get("frame_count") != summary["presentation_frame_count"]
    ):
        raise ValueError("presentation frame_count disagrees with summary")


def build_manifest(
    evidence_root: Path | str,
    *,
    require_auxiliary: bool = True,
    video_probe: Callable[[Path], Mapping[str, object]] = probe_video,
) -> dict[str, object]:
    root = Path(evidence_root)
    runs: list[dict[str, object]] = []
    for summary_path in sorted(root.glob("*/summary.json")):
        run_dir = summary_path.parent
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        events_path = _safe_declared_file(run_dir, summary.get("events_file"), "events")
        video_path = _safe_declared_file(run_dir, summary.get("video_file"), "video")
        presentation_path = None
        if summary.get("presentation_file") is not None:
            presentation_path = _safe_declared_file(
                run_dir, summary.get("presentation_file"), "presentation"
            )
        scene_path = _safe_declared_file(run_dir, summary.get("scene_file"), "scene")
        validation = validate_scenario_events(
            load_events(events_path), expected_scenario=str(summary["scenario"])
        )
        _assert_summary(summary, validation)
        video = dict(video_probe(video_path))
        _assert_video(summary, video)
        presentation = None
        if presentation_path is not None:
            presentation = dict(video_probe(presentation_path))
            _assert_presentation(summary, presentation)
        files = {}
        declared_paths = [events_path, summary_path, scene_path, video_path]
        if presentation_path is not None:
            declared_paths.append(presentation_path)
        for path in declared_paths:
            files[path.name] = {"size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
        run_record = {
            "run_id": validation.run_id,
            "scenario": validation.scenario,
            "source": validation.source,
            "terminal_status": validation.terminal_status,
            "event_count": validation.event_count,
            "duration_s": validation.duration_s,
            "isaac_version": summary.get("isaac_version"),
            "controller": summary.get("controller"),
            "video_probe": video,
            "files": files,
        }
        if presentation is not None:
            run_record["presentation_probe"] = presentation
        runs.append(run_record)
    if not runs:
        raise ValueError(f"no validated evidence runs found below {root}")
    auxiliary_evidence: dict[str, dict[str, object]] = {}
    for relative_name in AUXILIARY_EVIDENCE_FILES:
        path = root / relative_name
        if not path.is_file():
            if require_auxiliary:
                raise ValueError(f"auxiliary evidence missing: {relative_name}")
            continue
        auxiliary_evidence[relative_name] = {
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return {
        "schema_version": "1.0",
        "runs": runs,
        "auxiliary_evidence": auxiliary_evidence,
    }
