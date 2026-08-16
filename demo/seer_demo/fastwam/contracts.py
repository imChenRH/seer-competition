"""Fail-closed evidence contracts for recorded Fast-WAM policy rollouts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..contracts import Event, ValidationSummary, validate_events


FASTWAM_SCENARIO = "fastwam_apple_plate"
FASTWAM_SOURCE = "fastwam_policy"
FASTWAM_SKILLS = (
    "ARM-PER-01",
    "ARM-PLAN-01",
    "WAM-ACT-01",
    "ARM-OP-01",
    "ARM-OP-02",
    "ARM-OP-03",
    "ARM-OP-04",
    "ARM-VER-01",
)
ACTION_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ActionRecord:
    schema_version: str
    run_id: str
    sequence: int
    observed_frame: int
    sim_time_s: float
    action: tuple[float, ...]
    model_call: bool
    latency_s: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ActionRecord":
        known = {field.name for field in cls.__dataclass_fields__.values()}
        missing = sorted(known.difference(value))
        if missing:
            raise ValueError(f"action record missing required fields: {', '.join(missing)}")
        unknown = sorted(set(value).difference(known))
        if unknown:
            raise ValueError(f"action record contains unknown fields: {', '.join(unknown)}")
        action = value["action"]
        if not isinstance(action, (list, tuple)):
            raise ValueError("action must be an array")
        return cls(
            schema_version=value["schema_version"],
            run_id=value["run_id"],
            sequence=value["sequence"],
            observed_frame=value["observed_frame"],
            sim_time_s=value["sim_time_s"],
            action=tuple(action),
            model_call=value["model_call"],
            latency_s=value["latency_s"],
        )


@dataclass(frozen=True, slots=True)
class ActionValidationSummary:
    run_id: str
    action_count: int
    policy_call_count: int
    duration_s: float


def _finite_number(value: object, label: str, *, minimum: float | None = None) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return number


def _validate_action_record(
    record: ActionRecord, expected_run_id: str, index: int, frame_count: int
) -> None:
    if record.schema_version != ACTION_SCHEMA_VERSION:
        raise ValueError(f"unsupported action schema_version {record.schema_version!r}")
    if record.run_id != expected_run_id:
        raise ValueError(f"action run_id changed at sequence {index}")
    if type(record.sequence) is not int or record.sequence != index:
        raise ValueError(
            f"action sequence mismatch at index {index}: expected {index}, got {record.sequence}"
        )
    if type(record.observed_frame) is not int or not 0 <= record.observed_frame < frame_count:
        raise ValueError("observed_frame must reference an existing source-video frame")
    _finite_number(record.sim_time_s, "sim_time_s", minimum=0.0)
    if len(record.action) != 7:
        raise ValueError("Fast-WAM action must contain exactly seven values")
    for component in record.action:
        number = _finite_number(component, "action component")
        if not -1.0 <= number <= 1.0:
            raise ValueError("Fast-WAM action components must remain in [-1, 1]")
    if type(record.model_call) is not bool:
        raise ValueError("model_call must be boolean")
    _finite_number(record.latency_s, "latency_s", minimum=0.0)


def load_action_records(path: Path | str) -> list[ActionRecord]:
    records: list[ActionRecord] = []
    for line_number, raw_line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
            if not isinstance(value, dict):
                raise ValueError("action record must be a JSON object")
            records.append(ActionRecord.from_dict(value))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid action JSONL at line {line_number}: {exc}") from exc
    return records


def validate_action_records(
    records: Iterable[ActionRecord], run_id: str, frame_count: int
) -> ActionValidationSummary:
    materialized = list(records)
    if not materialized:
        raise ValueError("action log is empty")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string")
    if type(frame_count) is not int or frame_count <= 0:
        raise ValueError("frame_count must be a positive integer")
    previous_time = -1.0
    previous_frame = -1
    for index, record in enumerate(materialized):
        _validate_action_record(record, run_id, index, frame_count)
        if record.sim_time_s < previous_time:
            raise ValueError("action sim_time_s must be monotonic")
        if record.observed_frame < previous_frame:
            raise ValueError("action observed_frame must be monotonic")
        previous_time = record.sim_time_s
        previous_frame = record.observed_frame
    return ActionValidationSummary(
        run_id=run_id,
        action_count=len(materialized),
        policy_call_count=sum(record.model_call for record in materialized),
        duration_s=float(materialized[-1].sim_time_s),
    )


def _signature(event: Event) -> tuple[str, str | None]:
    return event.event_type, event.skill_id


def validate_fastwam_events(events: Iterable[Event]) -> ValidationSummary:
    materialized = list(events)
    summary = validate_events(materialized, expected_scenario=FASTWAM_SCENARIO)
    if summary.source != FASTWAM_SOURCE:
        raise ValueError(f"Fast-WAM trace requires source {FASTWAM_SOURCE}")
    if materialized[0].event_type != "task_started":
        raise ValueError("Fast-WAM trace must begin with task_started")

    body = materialized[1:-1]
    terminal = materialized[-1]
    completed_verification = any(
        event.event_type == "skill_completed" and event.skill_id == "ARM-VER-01"
        for event in body
    )
    if terminal.event_type == "task_completed":
        expected = []
        for skill_id in FASTWAM_SKILLS:
            expected.extend((("skill_started", skill_id), ("skill_completed", skill_id)))
        if [_signature(event) for event in body] != expected:
            raise ValueError("successful Fast-WAM trace does not match the exact skill chain")
        verification = body[-1]
        if verification.state.get("official_success") is not True:
            raise ValueError("ARM-VER-01 requires official_success=true")
        if terminal.state.get("official_success") is not True:
            raise ValueError("completed Fast-WAM task requires official_success=true")
    elif terminal.event_type == "task_failed":
        if completed_verification:
            raise ValueError("failed Fast-WAM trace may not complete ARM-VER-01")
        expected_index = 0
        expecting_started = True
        for event in body:
            if expected_index >= len(FASTWAM_SKILLS):
                raise ValueError("failed Fast-WAM trace contains skills after verification")
            expected_type = "skill_started" if expecting_started else "skill_completed"
            if _signature(event) != (expected_type, FASTWAM_SKILLS[expected_index]):
                raise ValueError("failed Fast-WAM trace is not an ordered skill-prefix")
            if expecting_started:
                expecting_started = False
            else:
                expecting_started = True
                expected_index += 1
        if terminal.state.get("official_success") is not False:
            raise ValueError("failed Fast-WAM task requires official_success=false")
    else:
        raise ValueError("Fast-WAM task must end with task_completed or task_failed")
    return summary


def _require_exact_summary_field(
    summary: Mapping[str, Any], key: str, expected: object
) -> None:
    if summary.get(key) != expected:
        raise ValueError(f"summary field {key} does not match validated evidence")


def validate_fastwam_package(
    summary: Mapping[str, Any],
    events: Iterable[Event],
    actions: Iterable[ActionRecord],
) -> ValidationSummary:
    if not isinstance(summary, Mapping):
        raise ValueError("summary must be an object")
    materialized_events = list(events)
    materialized_actions = list(actions)
    event_validation = validate_fastwam_events(materialized_events)
    frame_count = summary.get("frame_count")
    if type(frame_count) is not int or frame_count <= 0:
        raise ValueError("summary frame_count must be a positive integer")
    action_validation = validate_action_records(
        materialized_actions, event_validation.run_id, frame_count
    )
    for key in (
        "run_id",
        "scenario",
        "source",
        "event_count",
        "terminal_status",
        "duration_s",
    ):
        _require_exact_summary_field(summary, key, getattr(event_validation, key))
    _require_exact_summary_field(summary, "action_count", action_validation.action_count)
    _require_exact_summary_field(
        summary, "policy_call_count", action_validation.policy_call_count
    )
    _require_exact_summary_field(summary, "attempt_count", 5)

    attempts = summary.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 5:
        raise ValueError("summary attempts must contain exactly five results")
    successes: list[int] = []
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, Mapping):
            raise ValueError("attempt result must be an object")
        if attempt.get("attempt_index") != index:
            raise ValueError("attempt indices must be contiguous from zero")
        if type(attempt.get("seed")) is not int or type(attempt.get("init_state_id")) is not int:
            raise ValueError("attempt seed and init_state_id must be integers")
        if type(attempt.get("success")) is not bool:
            raise ValueError("attempt success must be boolean")
        if type(attempt.get("executed_steps")) is not int or attempt["executed_steps"] < 0:
            raise ValueError("attempt executed_steps must be a non-negative integer")
        if type(attempt.get("policy_calls")) is not int or attempt["policy_calls"] < 0:
            raise ValueError("attempt policy_calls must be a non-negative integer")
        if not isinstance(attempt.get("terminal_reason"), str) or not attempt["terminal_reason"]:
            raise ValueError("attempt terminal_reason must be a non-empty string")
        if attempt["success"]:
            successes.append(index)
    selected = summary.get("selected_attempt")
    official_success = bool(successes)
    expected_selected = successes[0] if successes else None
    if selected != expected_selected:
        raise ValueError("selected_attempt must identify the first successful attempt")
    _require_exact_summary_field(summary, "official_success", official_success)
    if official_success != (event_validation.terminal_status == "COMPLETED"):
        raise ValueError("attempt outcomes disagree with terminal event status")
    return event_validation
