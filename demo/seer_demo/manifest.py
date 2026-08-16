"""Build a machine-verifiable manifest for recorded evidence runs."""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Mapping

from .contracts import load_events, validate_scenario_events
from .fastwam.contracts import (
    FASTWAM_SOURCE,
    load_action_records,
    validate_action_records,
    validate_fastwam_package,
)
from .isaac.collision import COLLISION_GUARD_VERSION


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


def _additional_evidence_paths(run_dir: Path, summary: Mapping[str, object]) -> list[Path]:
    values = summary.get("additional_evidence_files", [])
    if not isinstance(values, list):
        raise ValueError("additional_evidence_files must be an array")
    if any(not isinstance(value, str) for value in values):
        raise ValueError("additional_evidence_files must contain only filenames")
    if len(values) != len(set(values)):
        raise ValueError("additional_evidence_files must not contain duplicates")
    return [_safe_declared_file(run_dir, value, "additional evidence") for value in values]


def _validate_fastwam_attempt_evidence(
    run_dir: Path,
    summary: Mapping[str, object],
    additional_paths: list[Path],
    video_probe: Callable[[Path], Mapping[str, object]],
) -> None:
    attempts = summary["attempts"]
    expected_names = {"actions.jsonl", "evaluation.json"}
    for index in range(5):
        expected_names.update(
            {
                f"attempt-{index}-actions.jsonl",
                f"attempt-{index}-states.json",
                f"attempt-{index}-simulation.mp4",
            }
        )
    actual_names = {path.name for path in additional_paths}
    if actual_names != expected_names:
        raise ValueError("Fast-WAM additional evidence must declare every attempt artifact")

    resolution = str(summary["resolution"])
    expected_width, expected_height = (int(value) for value in resolution.split("x"))
    expected_fps = float(summary["fps"])
    for index, attempt in enumerate(attempts):
        action_path = run_dir / f"attempt-{index}-actions.jsonl"
        state_path = run_dir / f"attempt-{index}-states.json"
        video_path = run_dir / f"attempt-{index}-simulation.mp4"
        states = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(states, list) or len(states) != attempt["executed_steps"] + 1:
            raise ValueError(f"attempt {index} states do not match executed_steps")
        if any(
            not isinstance(state, dict) or type(state.get("official_success")) is not bool
            for state in states
        ):
            raise ValueError(f"attempt {index} states require boolean official_success")
        if any(state["official_success"] for state in states[:-1]):
            raise ValueError(f"attempt {index} continued after official_success")
        if states[-1]["official_success"] is not attempt["success"]:
            raise ValueError(f"attempt {index} final official_success disagrees with result")
        if (attempt["terminal_reason"] == "official_success") is not attempt["success"]:
            raise ValueError(f"attempt {index} terminal_reason disagrees with success")

        actions = load_action_records(action_path)
        action_validation = validate_action_records(actions, str(summary["run_id"]), len(states))
        if action_validation.action_count != attempt["executed_steps"]:
            raise ValueError(f"attempt {index} actions do not match executed_steps")
        if action_validation.policy_call_count != attempt["policy_calls"]:
            raise ValueError(f"attempt {index} actions do not match policy_calls")
        if any(action.observed_frame != action.sequence + 1 for action in actions):
            raise ValueError(f"attempt {index} actions are not bound to consecutive frames")

        video = video_probe(video_path)
        if (video.get("width"), video.get("height")) != (
            expected_width,
            expected_height,
        ):
            raise ValueError(f"attempt {index} video resolution disagrees with summary")
        if abs(float(video.get("fps", -1)) - expected_fps) > 1e-6:
            raise ValueError(f"attempt {index} video fps disagrees with summary")
        if video.get("frame_count") != len(states):
            raise ValueError(f"attempt {index} video frames disagree with states")

    presented = summary.get("presented_attempt")
    selected = summary.get("selected_attempt")
    expected_presented = selected if selected is not None else 0
    if presented != expected_presented:
        raise ValueError("presented_attempt does not select the recorded rollout")
    if sha256_file(run_dir / "actions.jsonl") != sha256_file(
        run_dir / f"attempt-{presented}-actions.jsonl"
    ):
        raise ValueError("presented actions do not match the selected attempt")
    if sha256_file(run_dir / "simulation.mp4") != sha256_file(
        run_dir / f"attempt-{presented}-simulation.mp4"
    ):
        raise ValueError("presented video does not match the selected attempt")


def assert_collision_summary(summary: Mapping[str, object]) -> None:
    """Reject self-declared certification unless every bound is coherent."""
    numeric_clearance = summary.get("minimum_body_clearance_m")
    numeric_contact_error = summary.get("maximum_contact_error_m")
    numeric_placement_error = summary.get("maximum_horizontal_placement_error_m")
    valid_collision_certification = (
        summary.get("collision_guard") == COLLISION_GUARD_VERSION
        and summary.get("collision_check_semantics")
        == "z-overlapping SAT candidate pairs after explicit allowed-contact filtering"
        and summary.get("collision_certified") is True
        and type(summary.get("collision_check_count")) is int
        and int(summary["collision_check_count"]) > 0
        and type(summary.get("forbidden_collision_count")) is int
        and int(summary["forbidden_collision_count"]) == 0
        and type(summary.get("obstacle_interpenetration_count")) is int
        and int(summary["obstacle_interpenetration_count"]) == 0
        and isinstance(numeric_clearance, (int, float))
        and not isinstance(numeric_clearance, bool)
        and math.isfinite(float(numeric_clearance))
        and float(numeric_clearance) >= 0.05
        and summary.get("maximum_allowed_contact_error_m") == 0.01
        and isinstance(numeric_contact_error, (int, float))
        and not isinstance(numeric_contact_error, bool)
        and math.isfinite(float(numeric_contact_error))
        and 0.0 <= float(numeric_contact_error) <= 0.01
        and type(summary.get("contact_violation_count")) is int
        and int(summary["contact_violation_count"]) == 0
        and summary.get("maximum_allowed_horizontal_placement_error_m") == 0.02
        and isinstance(numeric_placement_error, (int, float))
        and not isinstance(numeric_placement_error, bool)
        and math.isfinite(float(numeric_placement_error))
        and 0.0 <= float(numeric_placement_error) <= 0.02
    )
    if not valid_collision_certification:
        raise ValueError("Isaac summary lacks valid collision certification")


def assert_summary_matches_validation(
    summary: Mapping[str, object], validation
) -> None:
    for key in ("run_id", "scenario", "source", "event_count", "terminal_status", "duration_s"):
        actual = getattr(validation, key)
        if summary.get(key) != actual:
            raise ValueError(f"summary {key} disagrees with validated events")
    if validation.source == "isaac_sim":
        assert_collision_summary(summary)


def assert_video_matches_summary(
    summary: Mapping[str, object], video: Mapping[str, object]
) -> None:
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
        events = load_events(events_path)
        additional_paths = _additional_evidence_paths(run_dir, summary)
        actions_path = None
        if summary.get("source") == FASTWAM_SOURCE:
            actions_path = _safe_declared_file(
                run_dir, summary.get("actions_file"), "actions"
            )
            validation = validate_fastwam_package(
                summary, events, load_action_records(actions_path)
            )
            evaluation_path = _safe_declared_file(
                run_dir, "evaluation.json", "evaluation"
            )
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            if not isinstance(evaluation, dict) or evaluation.get("attempts") != summary.get("attempts"):
                raise ValueError("evaluation attempt results disagree with summary")
            _validate_fastwam_attempt_evidence(
                run_dir, summary, additional_paths, video_probe
            )
        else:
            validation = validate_scenario_events(
                events, expected_scenario=str(summary["scenario"])
            )
        assert_summary_matches_validation(summary, validation)
        video = dict(video_probe(video_path))
        assert_video_matches_summary(summary, video)
        presentation = None
        if presentation_path is not None:
            presentation = dict(video_probe(presentation_path))
            _assert_presentation(summary, presentation)
        files = {}
        declared_paths = [events_path, summary_path, scene_path, video_path]
        if actions_path is not None:
            declared_paths.append(actions_path)
        declared_paths.extend(additional_paths)
        if presentation_path is not None:
            declared_paths.append(presentation_path)
        for path in dict.fromkeys(declared_paths):
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
            "collision_guard": summary.get("collision_guard"),
            "collision_check_count": summary.get("collision_check_count"),
            "minimum_body_clearance_m": summary.get("minimum_body_clearance_m"),
            "maximum_contact_error_m": summary.get("maximum_contact_error_m"),
            "maximum_horizontal_placement_error_m": summary.get(
                "maximum_horizontal_placement_error_m"
            ),
            "contact_violation_count": summary.get("contact_violation_count"),
            "forbidden_collision_count": summary.get("forbidden_collision_count"),
            "obstacle_interpenetration_count": summary.get(
                "obstacle_interpenetration_count"
            ),
            "collision_certified": summary.get("collision_certified"),
            "video_probe": video,
            "files": files,
        }
        if presentation is not None:
            run_record["presentation_probe"] = presentation
        if validation.source == FASTWAM_SOURCE:
            run_record.update(
                {
            "policy_checkpoint": summary.get("policy_checkpoint"),
            "policy_repository": summary.get("policy_repository"),
            "policy_revision": summary.get("policy_revision"),
            "policy_config_sha256": summary.get("policy_config_sha256"),
            "policy_weights_sha256": summary.get("policy_weights_sha256"),
            "official_success": summary.get("official_success"),
                    "attempt_count": summary.get("attempt_count"),
                    "success_count": sum(
                        attempt["success"] is True for attempt in summary["attempts"]
                    ),
                    "selected_attempt": summary.get("selected_attempt"),
                }
            )
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
