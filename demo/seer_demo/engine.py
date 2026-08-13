"""Task state machine; the backend executes actions but cannot invent success."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Protocol

from .contracts import EventWriter
from .scenarios import SKILL_SEQUENCE, get_scenario


@dataclass(frozen=True, slots=True)
class ActionResult:
    success: bool
    duration_s: float
    state: Mapping[str, Any]
    evidence: Mapping[str, Any]
    message: str


class DemoBackend(Protocol):
    def execute_skill(self, skill_id: str, attempt: int) -> ActionResult: ...

    def execute_fallback(self, fallback_id: str, attempt: int) -> ActionResult: ...

    def safety_stop(self) -> ActionResult: ...

    def snapshot(self) -> Mapping[str, Any]: ...

    def snapshot_evidence(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class RunResult:
    scenario: str
    status: str
    sim_time_s: float
    completed_skills: tuple[str, ...]
    fallback_ids: tuple[str, ...]


class DemoEngine:
    def __init__(self, backend: DemoBackend, writer: EventWriter):
        self.backend = backend
        self.writer = writer
        self.sim_time_s = 0.0
        self.completed_skills: list[str] = []
        self.fallback_ids: list[str] = []

    def run(self, scenario_name: str) -> RunResult:
        scenario = get_scenario(scenario_name)
        self.writer.emit(
            "task_started",
            self.sim_time_s,
            status="RUNNING",
            message=scenario.instruction,
            state=self.backend.snapshot(),
            evidence={"controller": "deterministic_rule_engine"},
        )
        for skill_id in SKILL_SEQUENCE:
            if scenario_name == "recovery" and skill_id == "FORK-PER-01":
                self._run_recovery_perception(skill_id)
            elif scenario_name == "intervention" and skill_id == "FORK-PER-01":
                return self._run_intervention(skill_id)
            else:
                self._run_required_skill(skill_id, attempt=1)
        self.writer.emit(
            "task_completed",
            self.sim_time_s,
            status="COMPLETED",
            message="九技能任务完成",
            state=self.backend.snapshot(),
            evidence={
                **self.backend.snapshot_evidence(),
                "completed_skill_count": len(self.completed_skills),
            },
        )
        return self._result("COMPLETED")

    def _run_required_skill(self, skill_id: str, attempt: int) -> None:
        self.writer.emit(
            "skill_started",
            self.sim_time_s,
            status="RUNNING",
            skill_id=skill_id,
            message=f"开始执行 {skill_id}",
            state=self.backend.snapshot(),
            evidence={"attempt": attempt},
        )
        result = self.backend.execute_skill(skill_id, attempt)
        self.sim_time_s += result.duration_s
        if not result.success:
            self.writer.emit(
                "skill_failed",
                self.sim_time_s,
                status="RUNNING",
                skill_id=skill_id,
                message=result.message,
                state=result.state,
                evidence={**result.evidence, "attempt": attempt},
            )
            raise RuntimeError(f"required skill {skill_id} failed without a configured recovery")
        self.completed_skills.append(skill_id)
        self.writer.emit(
            "skill_completed",
            self.sim_time_s,
            status="RUNNING",
            skill_id=skill_id,
            message=result.message,
            state=result.state,
            evidence={**result.evidence, "attempt": attempt},
        )

    def _run_recovery_perception(self, skill_id: str) -> None:
        self.writer.emit(
            "skill_started",
            self.sim_time_s,
            status="RUNNING",
            skill_id=skill_id,
            message="首次位姿校验",
            state=self.backend.snapshot(),
            evidence={"attempt": 1},
        )
        first = self.backend.execute_skill(skill_id, 1)
        self.sim_time_s += first.duration_s
        if first.success:
            raise RuntimeError("recovery scenario did not produce its declared first-attempt offset")
        self.writer.emit(
            "skill_failed",
            self.sim_time_s,
            status="FALLBACK",
            skill_id=skill_id,
            message=first.message,
            state=first.state,
            evidence={**first.evidence, "attempt": 1},
        )
        self._start_fallback("FB-F01", skill_id, "栈板偏移超限，执行重新识别和对位")
        recovered = self.backend.execute_fallback("FB-F01", 1)
        self.sim_time_s += recovered.duration_s
        if not recovered.success:
            raise RuntimeError("FB-F01 recovery backend failed")
        self.writer.emit(
            "fallback_completed",
            self.sim_time_s,
            status="RUNNING",
            skill_id=skill_id,
            fallback_id="FB-F01",
            message=recovered.message,
            state=recovered.state,
            evidence={**recovered.evidence, "attempt": 1},
        )
        self._run_required_skill(skill_id, attempt=2)

    def _run_intervention(self, skill_id: str) -> RunResult:
        for attempt in range(1, 4):
            self.writer.emit(
                "skill_started",
                self.sim_time_s,
                status="RUNNING" if attempt == 1 else "FALLBACK",
                skill_id=skill_id,
                message=f"遮挡条件下第 {attempt} 次识别",
                state=self.backend.snapshot(),
                evidence={"attempt": attempt},
            )
            failed = self.backend.execute_skill(skill_id, attempt)
            self.sim_time_s += failed.duration_s
            if failed.success:
                raise RuntimeError("intervention scenario unexpectedly recovered")
            self.writer.emit(
                "skill_failed",
                self.sim_time_s,
                status="FALLBACK",
                skill_id=skill_id,
                fallback_id="FB-F02",
                message=failed.message,
                state=failed.state,
                evidence={**failed.evidence, "attempt": attempt},
            )
            if attempt == 1:
                self._start_fallback("FB-F02", skill_id, "调整视角并补充观测")
            if attempt < 3:
                adjusted = self.backend.execute_fallback("FB-F02", attempt)
                self.sim_time_s += adjusted.duration_s
                if not adjusted.success:
                    raise RuntimeError(f"FB-F02 view adjustment failed on attempt {attempt}")
                self.writer.emit(
                    "fallback_completed",
                    self.sim_time_s,
                    status="FALLBACK",
                    skill_id=skill_id,
                    fallback_id="FB-F02",
                    message=adjusted.message,
                    state=adjusted.state,
                    evidence={**adjusted.evidence, "attempt": attempt},
                )
        self._start_fallback("FB-F07", skill_id, "三次识别失败，请求人工介入")
        retreat = self.backend.execute_fallback("FB-F07", 1)
        self.sim_time_s += retreat.duration_s
        if not retreat.success:
            raise RuntimeError("FB-F07 safe retreat failed")
        self.writer.emit(
            "fallback_completed",
            self.sim_time_s,
            status="FALLBACK",
            skill_id=skill_id,
            fallback_id="FB-F07",
            message=retreat.message,
            state=retreat.state,
            evidence={**retreat.evidence, "attempt": 1},
        )
        stopped = self.backend.safety_stop()
        self.sim_time_s += stopped.duration_s
        stop_speed = stopped.state.get("base_speed_mps")
        if (
            not stopped.success
            or stopped.state.get("stopped") is not True
            or not isinstance(stop_speed, (int, float))
            or isinstance(stop_speed, bool)
            or not math.isfinite(stop_speed)
            or abs(float(stop_speed)) > 0.01
        ):
            raise RuntimeError("safety stop did not verify a stopped vehicle")
        self.writer.emit(
            "safety_stop",
            self.sim_time_s,
            status="PAUSED",
            skill_id=skill_id,
            fallback_id="FB-F07",
            message=stopped.message,
            state=stopped.state,
            evidence=stopped.evidence,
        )
        self.writer.emit(
            "human_intervention_requested",
            self.sim_time_s,
            status="HUMAN_REQUIRED",
            skill_id=skill_id,
            fallback_id="FB-F07",
            message="车辆已停稳，等待操作员确认遮挡清除",
            state=self.backend.snapshot(),
            evidence={
                **self.backend.snapshot_evidence(),
                "retry_count": 3,
                "alert_required": True,
            },
        )
        return self._result("HUMAN_REQUIRED")

    def _start_fallback(self, fallback_id: str, skill_id: str, message: str) -> None:
        self.fallback_ids.append(fallback_id)
        self.writer.emit(
            "fallback_started",
            self.sim_time_s,
            status="FALLBACK",
            skill_id=skill_id,
            fallback_id=fallback_id,
            message=message,
            state=self.backend.snapshot(),
            evidence={"fallback_ordinal": len(self.fallback_ids)},
        )

    def _result(self, status: str) -> RunResult:
        return RunResult(
            scenario=self.writer.scenario,
            status=status,
            sim_time_s=self.sim_time_s,
            completed_skills=tuple(self.completed_skills),
            fallback_ids=tuple(self.fallback_ids),
        )
