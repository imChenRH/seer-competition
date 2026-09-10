"""Deterministic Mac-safe backend; intentionally not labeled as simulation."""

from __future__ import annotations

from copy import deepcopy

from ..engine import ActionResult
from ..scenarios import SKILL_DURATIONS_S, get_scenario


class DryRunBackend:
    def __init__(self, scenario: str):
        get_scenario(scenario)
        self.scenario = scenario
        self._state = {
            "base_x_m": -4.0,
            "base_y_m": 0.0,
            "base_speed_mps": 0.0,
            "mast_height_m": 0.18,
            "payload_attached": False,
            "payload_placed": False,
            "obstacle_visible": scenario == "intervention",
            "pallet_lateral_error_m": 0.0,
            "stopped": False,
        }

    def snapshot(self):
        return deepcopy(self._state)

    def snapshot_evidence(self):
        return {"backend": "dry_run", "observed": True}

    def execute_skill(self, skill_id: str, attempt: int) -> ActionResult:
        duration = SKILL_DURATIONS_S[skill_id]
        evidence = {"backend": "dry_run", "observed": True}
        if skill_id == "FORK-PER-01":
            if self.scenario == "recovery" and attempt == 1:
                self._state["pallet_lateral_error_m"] = 0.08
                return self._result(False, duration, evidence, "检测到 80 mm 横向偏移")
            if self.scenario == "intervention":
                confidence = (0.42, 0.38, 0.35)[attempt - 1]
                self._state["perception_confidence"] = confidence
                self._state["view_attempt"] = attempt
                return self._result(False, duration, {**evidence, "confidence": confidence}, "遮挡导致置信度不足")
            self._state["perception_confidence"] = 0.93
        elif skill_id == "FORK-NAV-01":
            self._state.update(
                base_x_m=1.1,
                base_speed_mps=0.0,
                navigation_target_error_m=0.0,
            )
        elif skill_id == "FORK-NAV-03":
            self._state.update(
                base_x_m=2.0,
                base_y_m=0.0,
                precision_alignment_error_m=0.0,
                navigation_target_error_m=0.0,
            )
        elif skill_id == "FORK-OP-01":
            self._state.update(payload_attached=True, fork_contact=True)
        elif skill_id == "FORK-OP-02":
            self._state.update(mast_height_m=1.05, payload_height_m=1.22)
        elif skill_id == "FORK-OP-03":
            self._state["fork_tilt_deg"] = 4.0
        elif skill_id == "FORK-NAV-02":
            self._state["base_x_m"] = -1.5
        elif skill_id == "FORK-OP-05":
            self._state.update(base_x_m=-5.7, aligned_with_conveyor=True)
        elif skill_id == "FORK-OP-04":
            self._state.update(
                mast_height_m=0.35,
                payload_height_m=0.55,
                payload_attached=False,
                payload_placed=True,
                payload_supported=True,
                payload_settled=True,
            )
        return self._result(True, duration, evidence, f"{skill_id} 状态验证通过")

    def execute_fallback(self, fallback_id: str, attempt: int) -> ActionResult:
        if fallback_id == "FB-F01":
            self._state.update(
                base_y_m=0.08,
                pallet_lateral_error_m=0.0,
                lateral_correction_m=0.08,
            )
            return self._result(True, 8.0, {"backend": "dry_run"}, "重新对位完成，横向误差归零")
        if fallback_id == "FB-F02":
            self._state["camera_lateral_offset_m"] = round(0.15 * attempt, 2)
            return self._result(True, 2.0, {"backend": "dry_run"}, "观察位姿已调整")
        if fallback_id == "FB-F07":
            self._state.update(base_x_m=-1.0, safe_retreat_complete=True)
            return self._result(True, 4.0, {"backend": "dry_run"}, "已退回箱外安全等待点")
        return self._result(False, 0.0, {"backend": "dry_run"}, f"不支持的 Fallback {fallback_id}")

    def safety_stop(self) -> ActionResult:
        self._state.update(base_speed_mps=0.0, stopped=True, brake_engaged=True)
        return self._result(True, 1.0, {"backend": "dry_run", "velocity_verified": 0.0}, "安全停车完成")

    def _result(self, success, duration_s, evidence, message):
        return ActionResult(
            success=success,
            duration_s=duration_s,
            state=self.snapshot(),
            evidence=evidence,
            message=message,
        )
