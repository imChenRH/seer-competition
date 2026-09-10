"""Canonical skill and fallback definitions for the three Demo scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


SKILL_SEQUENCE = (
    "FORK-NAV-01",
    "FORK-NAV-03",
    "FORK-PER-01",
    "FORK-OP-01",
    "FORK-OP-02",
    "FORK-OP-03",
    "FORK-NAV-02",
    "FORK-OP-05",
    "FORK-OP-04",
)

SKILL_DURATIONS_S = {
    "FORK-NAV-01": 10.0,
    "FORK-NAV-03": 8.0,
    "FORK-PER-01": 3.0,
    "FORK-OP-01": 4.0,
    "FORK-OP-02": 3.0,
    "FORK-OP-03": 2.0,
    "FORK-NAV-02": 10.0,
    "FORK-OP-05": 6.0,
    "FORK-OP-04": 5.0,
}


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    name: str
    title: str
    instruction: str
    expected_terminal_status: str


SCENARIOS = {
    "normal": ScenarioDefinition(
        name="normal",
        title="正常卸货",
        instruction="卸载3号集装箱货物到A区传送带",
        expected_terminal_status="COMPLETED",
    ),
    "recovery": ScenarioDefinition(
        name="recovery",
        title="栈板偏移自动恢复",
        instruction="继续卸货，处理2号栈板",
        expected_terminal_status="COMPLETED",
    ),
    "intervention": ScenarioDefinition(
        name="intervention",
        title="遮挡后安全停车与人工介入",
        instruction="处理被倒塌货物遮挡的3号栈板",
        expected_terminal_status="HUMAN_REQUIRED",
    ),
}


def get_scenario(name: str) -> ScenarioDefinition:
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise ValueError(f"unknown scenario {name!r}; choose from {sorted(SCENARIOS)}") from exc


def skill_state_succeeded(skill_id: str, state: Mapping[str, object]) -> bool:
    """Evaluate the observable postcondition shared by runners and evidence validation."""
    def number(name: str) -> float | None:
        if name not in state:
            return None
        value = state[name]
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    if skill_id == "FORK-NAV-01":
        target_error = number("navigation_target_error_m")
        if target_error is not None:
            return target_error <= 0.01
        base_x = number("base_x_m")
        return base_x is not None and base_x >= 0.45
    if skill_id == "FORK-NAV-03":
        target_error = number("navigation_target_error_m")
        if target_error is not None:
            return target_error <= 0.01
        alignment_error = number("precision_alignment_error_m")
        if alignment_error is not None:
            return alignment_error <= 0.01
        base_x = number("base_x_m")
        return base_x is not None and base_x >= 1.9
    if skill_id == "FORK-PER-01":
        error = number("pallet_lateral_error_m")
        return state.get("obstacle_visible") is False and error is not None and abs(error) <= 0.02
    if skill_id == "FORK-OP-01":
        return state.get("payload_attached") is True
    if skill_id == "FORK-OP-02":
        mast = number("mast_height_m")
        return state.get("payload_attached") is True and mast is not None and mast >= 1.0
    if skill_id == "FORK-OP-03":
        tilt = number("fork_tilt_deg")
        return state.get("payload_attached") is True and tilt is not None and tilt >= 3.5
    if skill_id == "FORK-NAV-02":
        base_x = number("base_x_m")
        return state.get("payload_attached") is True and base_x is not None and base_x <= -0.9
    if skill_id == "FORK-OP-05":
        base_x, base_y = number("base_x_m"), number("base_y_m")
        return state.get("payload_attached") is True and (
            state.get("aligned_with_conveyor") is True
            or (
                base_x is not None
                and base_y is not None
                and base_x <= -4.9
                and base_y <= -1.9
            )
        )
    if skill_id == "FORK-OP-04":
        return (
            state.get("payload_attached") is False
            and state.get("payload_placed") is True
            and state.get("payload_supported") is True
            and state.get("payload_settled") is True
        )
    return False


def fallback_state_succeeded(fallback_id: str, state: Mapping[str, object]) -> bool:
    """Evaluate observable fallback postconditions at every evidence boundary."""
    def number(name: str) -> float | None:
        if name not in state:
            return None
        value = state[name]
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    if fallback_id == "FB-F01":
        error = number("pallet_lateral_error_m")
        return error is not None and abs(error) <= 0.02
    if fallback_id == "FB-F02":
        camera_offset, base_y = number("camera_lateral_offset_m"), number("base_y_m")
        offsets = [abs(value) for value in (camera_offset, base_y) if value is not None]
        return bool(offsets) and max(offsets) >= 0.14
    if fallback_id == "FB-F07":
        base_x = number("base_x_m")
        return (
            base_x is not None
            and base_x <= -0.9
            and state.get("payload_attached") is False
            and state.get("safe_retreat_complete") is True
        )
    return False


def skill_state_failed_as_expected(
    scenario: str, skill_id: str, state: Mapping[str, object]
) -> bool:
    """Verify declared failure causes; missing observations always fail closed."""
    if skill_id != "FORK-PER-01":
        return False
    if scenario == "recovery":
        value = state.get("pallet_lateral_error_m")
        if isinstance(value, bool):
            return False
        try:
            return state.get("obstacle_visible") is False and abs(float(value)) > 0.02
        except (TypeError, ValueError):
            return False
    if scenario == "intervention":
        return state.get("obstacle_visible") is True
    return False
