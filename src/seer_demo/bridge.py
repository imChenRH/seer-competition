"""Idempotent task bridge: claim once, run once, replay validated events once."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Iterable, Mapping, Protocol, Sequence

from .contracts import Event, load_events, validate_scenario_events
from .scenarios import SKILL_SEQUENCE


TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class TaskRecord:
    record_id: str
    task_id: str
    scenario: str
    instruction: str
    skill_sequence: tuple[str, ...]
    status: str
    last_event_sequence: int = -1

    def copy_with(self, **changes):
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class RunExecution:
    exit_code: int
    events: tuple[Event, ...]
    error: str


@dataclass(frozen=True, slots=True)
class BridgeOutcome:
    task_id: str
    terminal_status: str
    event_count: int
    message: str


class BridgeClient(Protocol):
    def list_waiting_tasks(self) -> Sequence[TaskRecord]: ...

    def try_claim(self, record_id: str, claim_id: str) -> bool: ...

    def update_task(self, record_id: str, fields: Mapping[str, object]) -> None: ...

    def append_audit(self, task: TaskRecord, event: Event) -> None: ...


class TaskRunner(Protocol):
    def run(self, task: TaskRecord) -> RunExecution: ...

    def resume(self, task: TaskRecord) -> RunExecution: ...


class SubprocessRunner:
    """Run a CLI that writes `events.jsonl`; never uses a shell."""

    def __init__(self, command_prefix: Sequence[str], evidence_root: Path | str):
        if not command_prefix:
            raise ValueError("command_prefix must not be empty")
        self.command_prefix = tuple(command_prefix)
        self.evidence_root = Path(evidence_root)

    def run(self, task: TaskRecord) -> RunExecution:
        if not TASK_ID_PATTERN.fullmatch(task.task_id):
            raise ValueError("task_id must contain only letters, numbers, dot, underscore or hyphen")
        output_dir = self.evidence_root / task.task_id
        try:
            output_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return RunExecution(
                2,
                (),
                "execution directory already exists; use a new task_id for an explicit retry",
            )
        command = [
            *self.command_prefix,
            "--scenario",
            task.scenario,
            "--output-dir",
            str(output_dir),
            "--run-id",
            f"{task.task_id}-{task.scenario}",
        ]
        try:
            process = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=900,
            )
        except subprocess.TimeoutExpired:
            return RunExecution(124, (), "runner timed out after 900 seconds")
        if process.returncode != 0:
            error = process.stderr.strip() or process.stdout.strip() or f"runner exited {process.returncode}"
            return RunExecution(process.returncode, (), error[-2000:])
        try:
            events, artifact_hashes = self._load_package(task, require_receipt=False)
            receipt_path = output_dir / ".runner-complete.json"
            with receipt_path.open("x", encoding="utf-8") as stream:
                json.dump(
                    {
                        "schema_version": "1.0",
                        "run_id": f"{task.task_id}-{task.scenario}",
                        "scenario": task.scenario,
                        "files": artifact_hashes,
                    },
                    stream,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.write("\n")
        except (OSError, ValueError) as exc:
            return RunExecution(2, (), f"runner evidence invalid: {exc}")
        return RunExecution(0, events, "")

    def resume(self, task: TaskRecord) -> RunExecution:
        """Replay only a previously sealed execution; never starts a process."""
        if not TASK_ID_PATTERN.fullmatch(task.task_id):
            raise ValueError("task_id must contain only letters, numbers, dot, underscore or hyphen")
        try:
            events, _ = self._load_package(task, require_receipt=True)
        except (OSError, ValueError) as exc:
            return RunExecution(2, (), f"completed execution receipt invalid: {exc}")
        return RunExecution(0, events, "")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _load_package(
        self, task: TaskRecord, *, require_receipt: bool
    ) -> tuple[tuple[Event, ...], dict[str, str]]:
        output_dir = self.evidence_root / task.task_id
        required = ("events.jsonl", "summary.json", "scene.usda", "simulation.mp4")
        paths = {name: output_dir / name for name in required}
        missing = [name for name, path in paths.items() if not path.is_file()]
        if missing:
            raise ValueError(f"completed artifact missing: {', '.join(missing)}")
        artifact_hashes = {name: self._sha256(path) for name, path in paths.items()}
        expected_run_id = f"{task.task_id}-{task.scenario}"
        events = tuple(load_events(paths["events.jsonl"]))
        validation = validate_scenario_events(events, expected_scenario=task.scenario)
        if validation.run_id != expected_run_id or validation.source != "isaac_sim":
            raise ValueError("completed artifacts have the wrong run_id or source")
        summary = json.loads(paths["summary.json"].read_text(encoding="utf-8"))
        if not isinstance(summary, Mapping):
            raise ValueError("summary must be an object")
        exact = {
            "run_id": validation.run_id,
            "scenario": validation.scenario,
            "source": validation.source,
            "event_count": validation.event_count,
            "terminal_status": validation.terminal_status,
            "duration_s": validation.duration_s,
        }
        if any(summary.get(key) != value for key, value in exact.items()):
            raise ValueError("summary does not match validated events")
        if require_receipt:
            receipt_path = output_dir / ".runner-complete.json"
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise ValueError("completed execution receipt missing") from exc
            if (
                not isinstance(receipt, Mapping)
                or receipt.get("run_id") != expected_run_id
                or receipt.get("scenario") != task.scenario
                or receipt.get("files") != artifact_hashes
            ):
                raise ValueError("completed execution receipt or artifact hashes disagree")
        return events, artifact_hashes


class TaskBridge:
    def __init__(self, client: BridgeClient, runner: TaskRunner, bridge_id: str):
        if not bridge_id.strip():
            raise ValueError("bridge_id must not be empty")
        self.client = client
        self.runner = runner
        self.bridge_id = bridge_id

    def process_once(self) -> list[BridgeOutcome]:
        outcomes: list[BridgeOutcome] = []
        for task in self.client.list_waiting_tasks():
            claim_id = f"{self.bridge_id}:{task.task_id}"
            if not self.client.try_claim(task.record_id, claim_id):
                continue
            if not TASK_ID_PATTERN.fullmatch(task.task_id):
                outcomes.append(
                    self._fail(
                        task,
                        "task_id must contain only letters, numbers, dot, underscore or hyphen",
                    )
                )
                continue
            if task.skill_sequence != SKILL_SEQUENCE:
                outcomes.append(
                    self._fail(
                        task,
                        "task skill sequence does not match the canonical nine-skill contract",
                    )
                )
                continue
            try:
                execution = (
                    self.runner.resume(task)
                    if task.status in {"执行中", "Fallback中"}
                    else self.runner.run(task)
                )
            except Exception as exc:
                outcomes.append(
                    self._fail(task, f"runner raised {type(exc).__name__}: {str(exc)[:300]}")
                )
                continue
            if execution.exit_code != 0:
                outcomes.append(self._fail(task, execution.error or "runner failed"))
                continue
            try:
                summary = validate_scenario_events(
                    execution.events, expected_scenario=task.scenario
                )
            except ValueError as exc:
                outcomes.append(self._fail(task, f"evidence rejected: {exc}"))
                continue
            expected_run_id = f"{task.task_id}-{task.scenario}"
            if summary.run_id != expected_run_id:
                outcomes.append(
                    self._fail(
                        task,
                        f"evidence run_id mismatch: expected {expected_run_id!r}, got {summary.run_id!r}",
                    )
                )
                continue
            if summary.source != "isaac_sim":
                outcomes.append(
                    self._fail(
                        task,
                        f"evidence source mismatch: expected 'isaac_sim', got {summary.source!r}",
                    )
                )
                continue
            terminal_sequence = len(execution.events) - 1
            if (
                not isinstance(task.last_event_sequence, int)
                or isinstance(task.last_event_sequence, bool)
                or not -1 <= task.last_event_sequence <= terminal_sequence
            ):
                outcomes.append(
                    self._fail(
                        task,
                        "checkpoint is outside the validated event sequence range",
                    )
                )
                continue
            for event in execution.events:
                if event.sequence <= task.last_event_sequence:
                    continue
                self.client.append_audit(task, event)
                self.client.update_task(
                    task.record_id, self._fields_for_event(event, claim_id)
                )
            if task.last_event_sequence == terminal_sequence:
                terminal_event = execution.events[-1]
                self.client.update_task(
                    task.record_id, self._fields_for_event(terminal_event, claim_id)
                )
            outcomes.append(
                BridgeOutcome(
                    task_id=task.task_id,
                    terminal_status=summary.terminal_status,
                    event_count=summary.event_count,
                    message="validated evidence replayed",
                )
            )
        return outcomes

    def _fail(self, task: TaskRecord, message: str) -> BridgeOutcome:
        self.client.update_task(
            task.record_id,
            {"任务状态": "异常", "外部执行状态": f"执行失败：{message[:500]}"},
        )
        return BridgeOutcome(task.task_id, "FAILED", 0, message)

    @staticmethod
    def _fields_for_event(event: Event, claim_id: str) -> dict[str, object]:
        fields: dict[str, object] = {
            "外部执行状态": (
                f"CLAIMED:{claim_id}|{event.run_id}#{event.sequence}:{event.event_type}"
            ),
            "最后事件序号": event.sequence,
        }
        if event.skill_id:
            fields["当前技能"] = event.skill_id
        if event.fallback_id:
            fields["触发的Fallback"] = event.fallback_id
        if event.event_type == "task_started":
            fields["任务状态"] = "执行中"
        elif event.event_type == "fallback_started":
            fields["任务状态"] = "Fallback中"
        elif event.event_type == "task_completed":
            fields.update({"任务状态": "已完成", "外部执行状态": "任务完成"})
        elif event.event_type == "human_intervention_requested":
            fields.update({"任务状态": "人工介入", "外部执行状态": "安全停止，等待人工介入"})
        elif event.event_type == "task_failed":
            fields["任务状态"] = "异常"
        return fields
