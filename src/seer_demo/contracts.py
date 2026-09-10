"""Stable JSONL event contract shared by runners, bridge and console."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, TextIO


SCHEMA_VERSION = "1.0"
ALLOWED_SOURCES = frozenset(
    {"dry_run", "isaac_sim", "feishu_bridge", "fastwam_verification", "fastwam_policy"}
)
ALLOWED_STATUSES = frozenset(
    {"PENDING", "RUNNING", "FALLBACK", "PAUSED", "COMPLETED", "FAILED", "HUMAN_REQUIRED"}
)
ALLOWED_EVENT_TYPES = frozenset(
    {
        "task_started",
        "skill_started",
        "skill_completed",
        "skill_failed",
        "fallback_started",
        "fallback_completed",
        "safety_stop",
        "human_intervention_requested",
        "task_completed",
        "task_failed",
    }
)
TERMINAL_EVENT_TYPES = frozenset(
    {"task_completed", "task_failed", "human_intervention_requested"}
)
TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "HUMAN_REQUIRED"})
TERMINAL_STATUS_BY_EVENT = {
    "task_completed": "COMPLETED",
    "task_failed": "FAILED",
    "human_intervention_requested": "HUMAN_REQUIRED",
}


@dataclass(frozen=True, slots=True)
class Event:
    schema_version: str
    run_id: str
    sequence: int
    scenario: str
    event_type: str
    source: str
    sim_time_s: float
    status: str
    occurred_at: str
    skill_id: str | None = None
    fallback_id: str | None = None
    message: str = ""
    state: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Event":
        required = {item.name for item in cls.__dataclass_fields__.values()}
        missing = sorted(required.difference(value))
        if missing:
            raise ValueError(f"event missing required fields: {', '.join(missing)}")
        known = {item.name for item in cls.__dataclass_fields__.values()}
        unknown = sorted(set(value).difference(known))
        if unknown:
            raise ValueError(f"event contains unknown fields: {', '.join(unknown)}")
        return cls(**{key: value[key] for key in known if key in value})

    def copy_with(self, **changes: Any) -> "Event":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    run_id: str
    scenario: str
    source: str
    event_count: int
    terminal_status: str
    duration_s: float


class EventWriter:
    def __init__(self, path: Path | str, run_id: str, scenario: str, source: str):
        if source not in ALLOWED_SOURCES:
            raise ValueError(f"source must be one of {sorted(ALLOWED_SOURCES)}, got {source!r}")
        if not run_id.strip():
            raise ValueError("run_id must not be empty")
        if not scenario.strip():
            raise ValueError("scenario must not be empty")
        self.path = Path(path)
        self.run_id = run_id
        self.scenario = scenario
        self.source = source
        self._sequence = 0
        self._file: TextIO | None = None

    def __enter__(self) -> "EventWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("x", encoding="utf-8")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def emit(
        self,
        event_type: str,
        sim_time_s: float,
        *,
        status: str,
        skill_id: str | None = None,
        fallback_id: str | None = None,
        message: str = "",
        state: Mapping[str, Any] | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> Event:
        if self._file is None:
            raise RuntimeError("EventWriter must be used as a context manager")
        event = Event(
            schema_version=SCHEMA_VERSION,
            run_id=self.run_id,
            sequence=self._sequence,
            scenario=self.scenario,
            event_type=event_type,
            source=self.source,
            sim_time_s=float(sim_time_s),
            status=status,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            skill_id=skill_id,
            fallback_id=fallback_id,
            message=message,
            state=dict(state or {}),
            evidence=dict(evidence or {}),
        )
        _validate_event_fields(event)
        self._file.write(json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
        self._file.flush()
        self._sequence += 1
        return event


def _validate_event_fields(event: Event) -> None:
    for name, value in (("run_id", event.run_id), ("scenario", event.scenario)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    for name, value in (
        ("schema_version", event.schema_version),
        ("source", event.source),
        ("status", event.status),
        ("event_type", event.event_type),
        ("occurred_at", event.occurred_at),
        ("message", event.message),
    ):
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
    for name, value in (("skill_id", event.skill_id), ("fallback_id", event.fallback_id)):
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name} must be a string or null")
    if event.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {event.schema_version!r}")
    if event.source not in ALLOWED_SOURCES:
        raise ValueError(f"unknown source {event.source!r}")
    if event.status not in ALLOWED_STATUSES:
        raise ValueError(f"unknown status {event.status!r}")
    if event.event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"unknown event_type {event.event_type!r}")
    if not isinstance(event.sequence, int) or isinstance(event.sequence, bool):
        raise ValueError("sequence must be an integer")
    if event.sequence < 0:
        raise ValueError("sequence must be non-negative")
    if (
        not isinstance(event.sim_time_s, (int, float))
        or isinstance(event.sim_time_s, bool)
        or not math.isfinite(event.sim_time_s)
    ):
        raise ValueError("sim_time_s must be finite")
    if event.sim_time_s < 0:
        raise ValueError("sim_time_s must be non-negative and monotonic")
    try:
        timestamp = datetime.fromisoformat(event.occurred_at)
    except (TypeError, ValueError) as exc:
        raise ValueError("occurred_at must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError("occurred_at must include a timezone")
    if not isinstance(event.state, Mapping) or not isinstance(event.evidence, Mapping):
        raise ValueError("state and evidence must be objects")
    expected_terminal_status = TERMINAL_STATUS_BY_EVENT.get(event.event_type)
    if expected_terminal_status is not None and event.status != expected_terminal_status:
        raise ValueError(
            f"{event.event_type} must use terminal status {expected_terminal_status}"
        )


def load_events(path: Path | str) -> list[Event]:
    events: list[Event] = []
    for line_number, raw_line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
            if not isinstance(value, dict):
                raise ValueError("event must be a JSON object")
            event = Event.from_dict(value)
            _validate_event_fields(event)
            events.append(event)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
    return events


def validate_events(
    events: Iterable[Event], expected_scenario: str | None = None
) -> ValidationSummary:
    materialized = list(events)
    if not materialized:
        raise ValueError("event log is empty")
    first = materialized[0]
    previous_time = -1.0
    terminal_indexes: list[int] = []
    for index, event in enumerate(materialized):
        _validate_event_fields(event)
        if event.sequence != index:
            raise ValueError(f"sequence mismatch at index {index}: expected {index}, got {event.sequence}")
        if event.run_id != first.run_id:
            raise ValueError(f"run_id changed at sequence {event.sequence}")
        if event.scenario != first.scenario:
            raise ValueError(f"scenario changed at sequence {event.sequence}")
        if event.source != first.source:
            raise ValueError(f"source changed at sequence {event.sequence}")
        if event.sim_time_s < previous_time:
            raise ValueError(f"sim_time_s must be monotonic at sequence {event.sequence}")
        previous_time = event.sim_time_s
        if event.event_type in TERMINAL_EVENT_TYPES:
            terminal_indexes.append(index)
    if expected_scenario is not None and first.scenario != expected_scenario:
        raise ValueError(f"scenario mismatch: expected {expected_scenario!r}, got {first.scenario!r}")
    if terminal_indexes != [len(materialized) - 1]:
        raise ValueError("exactly one terminal event is required and terminal must be last")
    terminal = materialized[-1]
    return ValidationSummary(
        run_id=first.run_id,
        scenario=first.scenario,
        source=first.source,
        event_count=len(materialized),
        terminal_status=terminal.status,
        duration_s=terminal.sim_time_s,
    )


def validate_scenario_events(
    events: Iterable[Event], expected_scenario: str | None = None
) -> ValidationSummary:
    """Validate the complete, declared Demo scenario rather than JSONL shape alone."""
    materialized = list(events)
    summary = validate_events(materialized, expected_scenario=expected_scenario)
    from .scenarios import (
        SKILL_SEQUENCE,
        fallback_state_succeeded,
        get_scenario,
        skill_state_failed_as_expected,
        skill_state_succeeded,
    )

    scenario = get_scenario(summary.scenario)
    if materialized[0].event_type != "task_started":
        raise ValueError("scenario trace must begin with task_started")
    if summary.terminal_status != scenario.expected_terminal_status:
        raise ValueError(
            f"scenario {summary.scenario} requires terminal status "
            f"{scenario.expected_terminal_status}, got {summary.terminal_status}"
        )

    def signature(
        event_type: str,
        status: str,
        skill_id: str | None = None,
        fallback_id: str | None = None,
    ) -> tuple[str, str, str | None, str | None]:
        return event_type, status, skill_id, fallback_id

    def completed_pair(skill_id: str) -> list[tuple[str, str, str | None, str | None]]:
        return [
            signature("skill_started", "RUNNING", skill_id),
            signature("skill_completed", "RUNNING", skill_id),
        ]

    expected_trace = [signature("task_started", "RUNNING")]
    if summary.scenario == "normal":
        for skill_id in SKILL_SEQUENCE:
            expected_trace.extend(completed_pair(skill_id))
        expected_trace.append(signature("task_completed", "COMPLETED"))
    elif summary.scenario == "recovery":
        for skill_id in SKILL_SEQUENCE[:2]:
            expected_trace.extend(completed_pair(skill_id))
        perception = "FORK-PER-01"
        expected_trace.extend(
            [
                signature("skill_started", "RUNNING", perception),
                signature("skill_failed", "FALLBACK", perception),
                signature("fallback_started", "FALLBACK", perception, "FB-F01"),
                signature("fallback_completed", "RUNNING", perception, "FB-F01"),
                *completed_pair(perception),
            ]
        )
        for skill_id in SKILL_SEQUENCE[3:]:
            expected_trace.extend(completed_pair(skill_id))
        expected_trace.append(signature("task_completed", "COMPLETED"))
    else:
        for skill_id in SKILL_SEQUENCE[:2]:
            expected_trace.extend(completed_pair(skill_id))
        perception = "FORK-PER-01"
        expected_trace.extend(
            [
                signature("skill_started", "RUNNING", perception),
                signature("skill_failed", "FALLBACK", perception, "FB-F02"),
                signature("fallback_started", "FALLBACK", perception, "FB-F02"),
                signature("fallback_completed", "FALLBACK", perception, "FB-F02"),
                signature("skill_started", "FALLBACK", perception),
                signature("skill_failed", "FALLBACK", perception, "FB-F02"),
                signature("fallback_completed", "FALLBACK", perception, "FB-F02"),
                signature("skill_started", "FALLBACK", perception),
                signature("skill_failed", "FALLBACK", perception, "FB-F02"),
                signature("fallback_started", "FALLBACK", perception, "FB-F07"),
                signature("fallback_completed", "FALLBACK", perception, "FB-F07"),
                signature("safety_stop", "PAUSED", perception, "FB-F07"),
                signature(
                    "human_intervention_requested",
                    "HUMAN_REQUIRED",
                    perception,
                    "FB-F07",
                ),
            ]
        )
    actual_trace = [
        signature(event.event_type, event.status, event.skill_id, event.fallback_id)
        for event in materialized
    ]
    if actual_trace != expected_trace:
        mismatch = next(
            (
                index
                for index, (actual, expected) in enumerate(
                    zip(actual_trace, expected_trace, strict=False)
                )
                if actual != expected
            ),
            min(len(actual_trace), len(expected_trace)),
        )
        raise ValueError(f"event trace mismatch at sequence {mismatch}")

    completed = tuple(
        event.skill_id for event in materialized if event.event_type == "skill_completed"
    )
    expected_completed = SKILL_SEQUENCE if summary.scenario != "intervention" else SKILL_SEQUENCE[:2]
    if completed != expected_completed:
        raise ValueError(
            f"completed skill sequence mismatch: expected {expected_completed!r}, got {completed!r}"
        )

    failed = tuple(
        event.skill_id for event in materialized if event.event_type == "skill_failed"
    )
    expected_failed = {
        "normal": (),
        "recovery": ("FORK-PER-01",),
        "intervention": ("FORK-PER-01",) * 3,
    }[summary.scenario]
    if failed != expected_failed:
        raise ValueError(
            f"failed skill sequence mismatch: expected {expected_failed!r}, got {failed!r}"
        )

    fallbacks = tuple(
        event.fallback_id for event in materialized if event.event_type == "fallback_started"
    )
    expected_fallbacks = {
        "normal": (),
        "recovery": ("FB-F01",),
        "intervention": ("FB-F02", "FB-F07"),
    }[summary.scenario]
    if fallbacks != expected_fallbacks:
        raise ValueError(
            f"fallback sequence mismatch: expected {expected_fallbacks!r}, got {fallbacks!r}"
        )

    for event in materialized:
        if event.event_type != "skill_completed":
            continue
        if not isinstance(event.state, Mapping) or not event.state:
            raise ValueError(f"skill_completed {event.skill_id} requires observed state")
        if event.source == "isaac_sim" and event.evidence.get("stage_observed") is not True:
            raise ValueError(f"Isaac skill_completed {event.skill_id} requires stage observation")
        if event.skill_id is None or not skill_state_succeeded(event.skill_id, event.state):
            raise ValueError(
                f"{event.skill_id} failed its observed state predicate despite skill_completed"
            )

    for event in materialized:
        if event.event_type != "skill_failed":
            continue
        if event.skill_id is None or not skill_state_failed_as_expected(
            summary.scenario, event.skill_id, event.state
        ):
            raise ValueError(
                f"{event.skill_id} failed its expected failure predicate for {summary.scenario}"
            )

    expected_skill_attempts = {
        "normal": {
            skill_id: [1, 1] for skill_id in SKILL_SEQUENCE
        },
        "recovery": {
            **{skill_id: [1, 1] for skill_id in SKILL_SEQUENCE if skill_id != "FORK-PER-01"},
            "FORK-PER-01": [1, 1, 2, 2],
        },
        "intervention": {
            "FORK-NAV-01": [1, 1],
            "FORK-NAV-03": [1, 1],
            "FORK-PER-01": [1, 1, 2, 2, 3, 3],
        },
    }[summary.scenario]
    for skill_id, expected_attempts in expected_skill_attempts.items():
        actual_attempts = [
            event.evidence.get("attempt")
            for event in materialized
            if event.skill_id == skill_id
            and event.event_type in {"skill_started", "skill_completed", "skill_failed"}
        ]
        if actual_attempts != expected_attempts:
            raise ValueError(
                f"{skill_id} attempt sequence mismatch: expected {expected_attempts}, got {actual_attempts}"
            )

    expected_fallback_attempts = {
        "normal": {},
        "recovery": {"FB-F01": [1]},
        "intervention": {"FB-F02": [1, 2], "FB-F07": [1]},
    }[summary.scenario]
    for fallback_id, expected_attempts in expected_fallback_attempts.items():
        actual_attempts = [
            event.evidence.get("attempt")
            for event in materialized
            if event.fallback_id == fallback_id and event.event_type == "fallback_completed"
        ]
        if actual_attempts != expected_attempts:
            raise ValueError(
                f"{fallback_id} attempt sequence mismatch: expected {expected_attempts}, got {actual_attempts}"
            )

    isaac_decisions = [
        event
        for event in materialized
        if event.source == "isaac_sim"
        and event.event_type
        in {
            "skill_completed",
            "skill_failed",
            "fallback_completed",
            "safety_stop",
            "task_completed",
            "human_intervention_requested",
        }
    ]
    for event in isaac_decisions:
        if event.evidence.get("stage_observed") is not True:
            raise ValueError(f"Isaac {event.event_type} requires stage observation")
        frame = event.evidence.get("observed_frame")
        if not isinstance(frame, int) or isinstance(frame, bool) or frame < 0:
            raise ValueError(f"Isaac {event.event_type} requires a non-negative observed_frame")
    observed_frames = [int(event.evidence["observed_frame"]) for event in isaac_decisions]
    if observed_frames != sorted(observed_frames):
        raise ValueError("Isaac observed_frame values must be monotonic")

    for event in materialized:
        if event.event_type != "fallback_completed":
            continue
        if event.source == "isaac_sim" and event.evidence.get("stage_observed") is not True:
            raise ValueError(
                f"Isaac fallback_completed {event.fallback_id} requires stage observation"
            )
        if event.fallback_id is None or not fallback_state_succeeded(
            event.fallback_id, event.state
        ):
            raise ValueError(
                f"{event.fallback_id} failed its observed state predicate despite fallback_completed"
            )

    if summary.scenario == "intervention":
        view_positions = []
        for event in materialized:
            if event.event_type == "fallback_completed" and event.fallback_id == "FB-F02":
                value = event.state.get("camera_lateral_offset_m")
                if value is None:
                    value = event.state.get("base_y_m")
                if isinstance(value, bool):
                    raise ValueError("FB-F02 view position must be numeric")
                try:
                    view_positions.append(float(value))
                except (TypeError, ValueError) as exc:
                    raise ValueError("FB-F02 view position must be numeric") from exc
        if len(view_positions) != 2 or abs(view_positions[0] - view_positions[1]) < 0.10:
            raise ValueError("FB-F02 attempts must use distinct observed view positions")

    if summary.scenario == "intervention":
        stops = [event for event in materialized if event.event_type == "safety_stop"]
        if len(stops) != 1 or stops[0].state.get("stopped") is not True:
            raise ValueError("intervention requires one observed stopped safety_stop event")
        stop_speed = stops[0].state.get("base_speed_mps")
        if (
            not isinstance(stop_speed, (int, float))
            or isinstance(stop_speed, bool)
            or not math.isfinite(stop_speed)
            or abs(float(stop_speed)) > 0.01
        ):
            raise ValueError("safety_stop requires finite base_speed_mps within 0.01 m/s")
        if stops[0].source == "isaac_sim" and stops[0].evidence.get("stage_observed") is not True:
            raise ValueError("Isaac safety_stop requires stage observation")
        terminal_state = materialized[-1].state
        if (
            terminal_state.get("stopped") is not True
            or terminal_state.get("safe_retreat_complete") is not True
            or terminal_state.get("payload_attached") is not False
        ):
            raise ValueError("intervention terminal state must remain stopped after safe retreat")
    else:
        terminal_state = materialized[-1].state
        if (
            terminal_state.get("payload_attached") is not False
            or terminal_state.get("payload_placed") is not True
        ):
            raise ValueError("completed terminal state must contain a released, placed payload")
    terminal = materialized[-1]
    preceding_decision = materialized[-2]
    if terminal.state != preceding_decision.state:
        raise ValueError("terminal observation must match the preceding decision state")
    if terminal.source == "isaac_sim" and terminal.evidence.get(
        "observed_frame"
    ) != preceding_decision.evidence.get("observed_frame"):
        raise ValueError("Isaac terminal observed_frame must match the preceding decision")
    return summary
