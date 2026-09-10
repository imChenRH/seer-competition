"""Adapt observable Fast-WAM evidence into the common split presentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .. import presentation as common_presentation
from ..contracts import Event
from .contracts import ActionRecord


FASTWAM_PRESENTATION_SIZE = common_presentation.CANVAS_SIZE

SKILL_DISPATCH: Mapping[str, str] = {
    "ARM-PER-01": "读取双视角图像与机械臂状态",
    "ARM-PLAN-01": "将碗放盘子目标映射为动作任务",
    "WAM-ACT-01": "调用 Fast-WAM 生成 7-D 相对动作",
    "ARM-OP-01": "控制末端接近黑色碗",
    "ARM-OP-02": "闭合夹爪并建立抓取",
    "ARM-OP-03": "举升并搬运黑色碗",
    "ARM-OP-04": "对准盘子并释放黑色碗",
    "ARM-VER-01": "验证官方 env.check_success() 谓词",
}


def action_at_frame(
    actions: Sequence[ActionRecord], frame: int
) -> ActionRecord | None:
    if type(frame) is not int or frame < 0:
        raise ValueError("frame must be a non-negative integer")
    visible = [action for action in actions if action.observed_frame <= frame]
    return visible[-1] if visible else None


def _visible_events(events: Sequence[Event], frame: int) -> list[Event]:
    visible = []
    for event in events:
        observed = event.evidence.get("observed_frame")
        if type(observed) is int and observed <= frame:
            visible.append(event)
    return visible


def _format_number(value: object, *, digits: int = 3, suffix: str = "") -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}{suffix}"
    return "—"


def fastwam_decision_snapshot(
    events: Iterable[Event],
    actions: Iterable[ActionRecord],
    summary: Mapping[str, Any],
    *,
    frame: int,
) -> dict[str, Any]:
    """Return the common presentation schema using only frame-visible evidence."""
    materialized_events = list(events)
    materialized_actions = list(actions)
    visible = _visible_events(materialized_events, frame)
    if not visible:
        raise ValueError("no observed Fast-WAM event exists at the requested frame")
    latest = visible[-1]
    current_skill = next(
        (event.skill_id for event in reversed(visible) if event.skill_id),
        None,
    ) or "ARM-PER-01"
    action = action_at_frame(materialized_actions, frame)
    action_values = (0.0,) * 7 if action is None else action.action
    observed_success = bool(
        latest.state.get("official_success") is True
        and latest.event_type in {"skill_completed", "task_completed"}
    )
    attempts = [
        value for value in summary.get("attempts", []) if isinstance(value, Mapping)
    ]
    successes = sum(value.get("success") is True for value in attempts)
    fps = summary.get("fps", 20)
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0:
        raise ValueError("Fast-WAM summary fps must be positive")
    recent = [
        {
            "sequence": event.sequence,
            "sim_time_s": round(
                float(event.evidence.get("observed_frame", 0)) / float(fps),
                3,
            ),
            "label": common_presentation.EVENT_LABELS.get(
                event.event_type, event.event_type
            ),
            "message": event.message
            or SKILL_DISPATCH.get(event.skill_id or "", ""),
            "status": event.status,
        }
        for event in visible[-3:]
    ]
    state = latest.state
    status = "COMPLETED" if observed_success else latest.status
    return {
        "run_id": latest.run_id,
        "scenario": latest.scenario,
        "source_title": "LIBERO / MUJOCO · FAST-WAM",
        "scene_label": "CANONICAL TASK 8 · OBSERVED POLICY CONTROL",
        "sim_time_s": round(frame / float(fps), 3),
        "goal": materialized_events[0].message,
        "status": status,
        "current_skill_id": current_skill,
        "fallback_id": None,
        "brain": {
            "mode": "NORMAL",
            "dispatch": SKILL_DISPATCH.get(current_skill, "保持当前动作任务"),
            "structured_intent": {
                "skill_id": current_skill,
                "fallback_id": None,
                "attempt": summary.get(
                    "presented_attempt", summary.get("selected_attempt")
                ),
            },
        },
        "cerebellum": {
            "controller": "Fast-WAM 7-D 相对动作",
            "action": action_values,
            "metrics": (
                (
                    "bowl_lift_m",
                    f"{_format_number(state.get('bowl_lift_m'), suffix=' m')}"
                    f" · error={_format_number(state.get('plate_xy_error_m'), suffix=' m')}",
                ),
                (
                    "grip / policy",
                    ("CLOSED" if state.get("gripper_closed") else "OPEN / TRANSITION")
                    + (" · MODEL CALL" if action and action.model_call else " · QUEUE"),
                ),
                (
                    "action xyz",
                    "/".join(f"{value:+.2f}" for value in action_values[:3]),
                ),
                (
                    "action rot/g",
                    "/".join(f"{value:+.2f}" for value in action_values[3:]),
                ),
            ),
        },
        "safety": {
            "gate": "CLEAR",
            "official_success": observed_success,
            "details": (
                ("predicate", "TRUE" if observed_success else "FALSE"),
                ("fixed_init", f"{successes}/{len(attempts) or 5} SUCCESS"),
                (
                    "latency",
                    _format_number(
                        None if action is None else action.latency_s,
                        suffix=" s",
                    ),
                ),
            ),
        },
        "audit": {
            "latest_sequence": latest.sequence,
            "event_type": latest.event_type,
            "recent": recent,
        },
    }


def render_fastwam_frames(
    events: Sequence[Event],
    actions: Sequence[ActionRecord],
    summary: Mapping[str, Any],
    output_dir: Path,
    *,
    frame_count: int,
    font_path: Path | None = None,
) -> Path:
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    output_dir.mkdir(parents=True, exist_ok=False)
    for frame in range(frame_count):
        snapshot = fastwam_decision_snapshot(
            events,
            actions,
            summary,
            frame=frame,
        )
        image = common_presentation.render_overlay(
            snapshot,
            frame_index=frame,
            frame_count=frame_count,
            font_path=font_path,
        )
        image.save(output_dir / f"frame-{frame:06d}.png", optimize=True)
    return output_dir / "frame-%06d.png"
