"""Synchronized, observation-only Fast-WAM presentation projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..contracts import Event
from ..presentation import _draw_text_lines, _fit_text, _load_font
from .contracts import ActionRecord


FASTWAM_PRESENTATION_SIZE = (2560, 1080)
ACTION_LABELS = ("dx", "dy", "dz", "drx", "dry", "drz", "grip")


@dataclass(frozen=True, slots=True)
class FastWamTheme:
    name: str
    accent: str
    card_fill: str
    background: str


@dataclass(frozen=True, slots=True)
class FastWamSnapshot:
    run_id: str
    frame: int
    phase: str
    status: str
    layer: str
    action: tuple[float, ...]
    model_call: bool
    latency_s: float | None
    state: Mapping[str, Any]
    latest_event_sequence: int
    official_success: bool
    selected_attempt: int | None
    attempts: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def fastwam_snapshot(
    events: Iterable[Event],
    actions: Iterable[ActionRecord],
    summary: Mapping[str, Any],
    *,
    frame: int,
) -> FastWamSnapshot:
    materialized_events = list(events)
    materialized_actions = list(actions)
    visible = _visible_events(materialized_events, frame)
    if not visible:
        raise ValueError("no observed Fast-WAM event exists at the requested frame")
    latest = visible[-1]
    current_skill = next((event.skill_id for event in reversed(visible) if event.skill_id), None)
    action = action_at_frame(materialized_actions, frame)
    values = (0.0,) * 7 if action is None else action.action
    observed_success = bool(
        latest.state.get("official_success") is True
        and latest.event_type in {"skill_completed", "task_completed"}
    )
    attempts = summary.get("attempts", [])
    return FastWamSnapshot(
        run_id=latest.run_id,
        frame=frame,
        phase=current_skill or "ARM-PER-01",
        status=latest.status,
        layer="Fast-WAM policy action",
        action=values,
        model_call=False if action is None else action.model_call,
        latency_s=None if action is None else action.latency_s,
        state=dict(latest.state),
        latest_event_sequence=latest.sequence,
        official_success=observed_success,
        selected_attempt=summary.get("selected_attempt"),
        attempts=tuple(dict(value) for value in attempts if isinstance(value, Mapping)),
    )


def fastwam_theme(snapshot: FastWamSnapshot) -> FastWamTheme:
    if snapshot.official_success:
        return FastWamTheme("VERIFIED", "#43D17C", "#0B3826", "#061C14")
    if snapshot.status == "FAILED":
        return FastWamTheme("FAILED", "#FF5D68", "#42161D", "#220B10")
    if snapshot.phase in {"ARM-OP-03", "ARM-OP-04"}:
        return FastWamTheme("TRANSFER", "#FFB547", "#3D2A10", "#211609")
    return FastWamTheme("RUNNING", "#4AA8FF", "#102F50", "#081A2B")


def _fmt(value: object, *, digits: int = 3) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "—" if value is None else str(value)


def render_fastwam_panel(
    snapshot: FastWamSnapshot,
    *,
    frame_count: int,
    font_path: Path | None = None,
):
    """Render a full transparent overlay containing the right evidence panel."""
    from PIL import Image, ImageDraw

    theme = fastwam_theme(snapshot)
    image = Image.new("RGBA", FASTWAM_PRESENTATION_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    navy = "#07111D"
    white = "#F2F7FA"
    muted = "#9EB3C5"
    cyan = "#3ED1E6"

    draw.rectangle((0, 0, 1280, 180), fill=navy)
    draw.rectangle((0, 900, 1280, 1080), fill=navy)
    draw.rectangle((1280, 0, 2560, 1080), fill=theme.background)
    draw.rectangle((1276, 0, 1284, 1080), fill=theme.accent)

    title = _load_font(42, bold=True, explicit=font_path)
    heading = _load_font(30, bold=True, explicit=font_path)
    body = _load_font(24, explicit=font_path)
    small = _load_font(19, explicit=font_path)
    value_font = _load_font(27, bold=True, explicit=font_path)

    draw.text((52, 35), "LIBERO / MUJOCO · FAST-WAM 实际控制", font=title, fill=white)
    draw.text((52, 106), "红苹果 → 黄盘 · 官方 task 8 视觉语义适配", font=body, fill=cyan)
    draw.text((52, 944), f"FRAME  {snapshot.frame:04d} / {frame_count - 1:04d}", font=heading, fill=white)
    draw.text((470, 950), f"PHASE  {snapshot.phase}", font=body, fill=muted)
    progress = 0.0 if frame_count <= 1 else min(1.0, snapshot.frame / (frame_count - 1))
    draw.rounded_rectangle((52, 1022, 1228, 1044), radius=10, fill="#17344B")
    draw.rounded_rectangle((52, 1022, 52 + int(1176 * progress), 1044), radius=10, fill=theme.accent)

    draw.text((1328, 28), "AGENTOS × FAST-WAM", font=title, fill=white)
    draw.text((1328, 84), "仅展示任务映射、实测动作、仿真观测与官方终态", font=small, fill=cyan)
    draw.rounded_rectangle((2315, 26, 2518, 82), radius=14, fill=theme.accent)
    draw.text((2340, 39), theme.name, font=heading, fill=navy)

    def card(box, label, fill=None):
        draw.rounded_rectangle(box, radius=16, fill=fill or theme.card_fill, outline="#355D79", width=2)
        draw.rectangle((box[0], box[1], box[0] + 7, box[3]), fill=theme.accent)
        draw.text((box[0] + 24, box[1] + 14), label, font=heading, fill=theme.accent)

    card((1320, 118, 2520, 260), "任务映射 / STRUCTURED DISPATCH")
    task_lines = _fit_text(
        draw,
        "把红色苹果放入黄色盘子  →  Put the bowl on the plate",
        body,
        1125,
        max_lines=2,
    )
    _draw_text_lines(draw, (1350, 172), task_lines, body, white, 7)

    card((1320, 282, 2520, 520), f"小脑动作 / {snapshot.layer}")
    card_width = 151
    for index, (label, value) in enumerate(zip(ACTION_LABELS, snapshot.action)):
        x = 1348 + index * 164
        draw.rounded_rectangle((x, 352, x + card_width, 438), radius=12, fill="#071B2B")
        draw.text((x + 14, 366), label, font=small, fill=muted)
        draw.text((x + 14, 398), f"{value:+.3f}", font=value_font, fill=white)
    latency = "—" if snapshot.latency_s is None else f"{snapshot.latency_s:.3f} s"
    marker = "新策略调用" if snapshot.model_call else "动作队列执行"
    draw.text((1350, 465), f"{marker} · 实测延迟 {latency}", font=body, fill=theme.accent)

    card((1320, 542, 1920, 796), "物理观测 / SIMULATOR")
    observations = (
        ("苹果举升", _fmt(snapshot.state.get("apple_lift_m")) + " m"),
        ("目标 XY 误差", _fmt(snapshot.state.get("plate_xy_error_m")) + " m"),
        ("夹爪", "闭合" if snapshot.state.get("gripper_closed") else "打开/过渡"),
        ("官方成功谓词", "TRUE" if snapshot.official_success else "FALSE"),
    )
    for index, (label, value) in enumerate(observations):
        y = 600 + index * 45
        draw.text((1350, y), label, font=small, fill=muted)
        draw.text((1600, y - 2), value, font=body, fill=white)

    card((1940, 542, 2520, 796), "五次固定初态 / ATTEMPTS")
    for index in range(5):
        attempt = snapshot.attempts[index] if index < len(snapshot.attempts) else {}
        success = attempt.get("success") is True
        color = "#43D17C" if success else "#FF5D68"
        y = 600 + index * 38
        draw.ellipse((1972, y + 2, 1990, y + 20), fill=color)
        draw.text((2005, y - 3), f"INIT {index}", font=small, fill=white)
        draw.text((2220, y - 3), "成功" if success else "未成功", font=small, fill=color)

    card((1320, 818, 2520, 1035), "证据边界 / CLAIM BOUNDARY", fill="#111F2B")
    boundary = (
        "绿色只在当前视频帧已经观测到 env.check_success() 后出现。"
        "本片不展示隐藏思维过程；也不证明苹果专项训练、实机迁移或生产安全。"
    )
    lines = _fit_text(draw, boundary, body, 1125, max_lines=3)
    _draw_text_lines(draw, (1350, 875), lines, body, white, 8)
    draw.text(
        (1350, 990),
        f"AUDIT  event={snapshot.latest_event_sequence} · selected={snapshot.selected_attempt}",
        font=small,
        fill=muted,
    )
    return image


def render_fastwam_frames(
    events: Sequence[Event],
    actions: Sequence[ActionRecord],
    summary: Mapping[str, Any],
    output_dir: Path,
    *,
    frame_count: int,
    font_path: Path | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=False)
    for frame in range(frame_count):
        snapshot = fastwam_snapshot(events, actions, summary, frame=frame)
        image = render_fastwam_panel(snapshot, frame_count=frame_count, font_path=font_path)
        image.save(output_dir / f"frame-{frame:06d}.png")
    return output_dir / "frame-%06d.png"
