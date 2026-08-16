"""Build an auditable brain/cerebellum presentation layer from JSONL events."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .contracts import Event
from .manifest import assert_collision_summary


CANVAS_SIZE = (2560, 1080)
VIDEO_BOX = (0, 180, 1280, 900)


@dataclass(frozen=True, slots=True)
class SkillPresentation:
    dispatch: str
    controller: str


@dataclass(frozen=True, slots=True)
class PresentationTheme:
    name: str
    accent: str
    card_fill: str
    right_background: str
    dispatch_font_size: int = 48
    section_font_size: int = 28


def presentation_theme(snapshot: Mapping[str, Any]) -> PresentationTheme:
    """Return a visually distinct theme for the observable execution state."""
    mode = snapshot["brain"]["mode"]
    status = snapshot["status"]
    if status == "COMPLETED":
        return PresentationTheme("COMPLETED", "#43D17C", "#0C3525", "#071B15")
    if status == "FAILED":
        return PresentationTheme("FAILED", "#FF5D68", "#401820", "#200C11")
    if mode in {"HUMAN_HANDOFF", "SAFETY_STOP"} or status == "HUMAN_REQUIRED":
        return PresentationTheme("SAFETY", "#FF5D68", "#401820", "#200C11")
    if mode == "RECOVERY" or status == "FALLBACK":
        return PresentationTheme("RECOVERY", "#FFB547", "#3D2A10", "#211609")
    return PresentationTheme("RUNNING", "#4AA8FF", "#102F50", "#081A2B")


SKILL_PRESENTATION: Mapping[str, SkillPresentation] = {
    "FORK-NAV-01": SkillPresentation("进入目标作业通道", "仓内路径跟踪"),
    "FORK-NAV-03": SkillPresentation("低速精确接近栈板", "末端位姿微调"),
    "FORK-PER-01": SkillPresentation("识别栈板并验证位姿", "多视角感知校验"),
    "FORK-OP-01": SkillPresentation("插入货叉并确认承载", "货叉深度闭环"),
    "FORK-OP-02": SkillPresentation("举升载荷", "货叉高度闭环"),
    "FORK-OP-03": SkillPresentation("后倾稳定载荷", "门架倾角闭环"),
    "FORK-NAV-02": SkillPresentation("携载退出作业通道", "携载路径跟踪"),
    "FORK-OP-05": SkillPresentation("对准目标传送带", "放置位姿对准"),
    "FORK-OP-04": SkillPresentation("下降并释放载荷", "接触与释放闭环"),
}

FALLBACK_PRESENTATION: Mapping[str, SkillPresentation] = {
    "FB-F01": SkillPresentation("重新识别并执行横向重对位", "横向重对位"),
    "FB-F02": SkillPresentation("调整观察位姿并补充观测", "观察位姿调整"),
    "FB-F07": SkillPresentation("停止自主任务并退回安全点", "安全撤退控制"),
}

EVENT_LABELS: Mapping[str, str] = {
    "task_started": "任务接收",
    "skill_started": "技能下发",
    "skill_completed": "技能验证",
    "skill_failed": "技能失败",
    "fallback_started": "恢复启动",
    "fallback_completed": "恢复验证",
    "safety_stop": "安全停车",
    "human_intervention_requested": "人工接管",
    "task_completed": "任务完成",
    "task_failed": "任务失败",
}


def frame_time_s(frame_index: int, fps: float) -> float:
    if not isinstance(frame_index, int) or isinstance(frame_index, bool) or frame_index < 0:
        raise ValueError("frame_index must be a non-negative integer")
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be positive and finite")
    return frame_index / float(fps)


def presentation_event_times(events: Sequence[Event], fps: float) -> list[float]:
    """Return one display-clock time per event, aligned to the rendered video.

    Evidence events carry a task-logic ``sim_time_s`` plus, for Isaac decision
    events, the exact ``observed_frame``. The presentation must use the same
    frame clock as the left-hand video, so observed events are projected at
    ``observed_frame / fps``. Non-observed events (starts and fallback starts)
    inherit the previous observed time, which keeps the event stream monotonic
    and keeps each start at the boundary of the action it belongs to.
    """
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be positive and finite")
    times: list[float] = []
    last_time = 0.0
    for event in events:
        frame = event.evidence.get("observed_frame")
        if (
            isinstance(frame, int)
            and not isinstance(frame, bool)
            and frame >= 0
        ):
            event_time = frame / float(fps)
        else:
            event_time = last_time
        event_time = max(event_time, last_time)
        times.append(round(event_time, 6))
        last_time = event_time
    return times


def _events_at(events: Sequence[Event], sim_time_s: float) -> list[Event]:
    return [event for event in events if event.sim_time_s <= sim_time_s + 1e-9]


def _current_skill(events: Sequence[Event]) -> str | None:
    for event in reversed(events):
        if event.skill_id:
            return event.skill_id
    return None


def _state_value(state: Mapping[str, Any], name: str, default: Any = None) -> Any:
    value = state.get(name, default)
    if isinstance(value, float):
        return round(value, 3)
    return value


def decision_snapshot(
    events: Iterable[Event],
    sim_time_s: float,
    *,
    collision_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project the event stream into display state without inventing hidden reasoning."""

    materialized = list(events)
    if collision_summary is not None:
        assert_collision_summary(collision_summary)
    visible = _events_at(materialized, sim_time_s)
    if not visible:
        raise ValueError("no event exists at or before the requested simulation time")
    latest = visible[-1]
    first = materialized[0]
    current_skill = _current_skill(visible)
    fallback_id = latest.fallback_id
    status = latest.status

    if latest.event_type == "human_intervention_requested":
        mode = "HUMAN_HANDOFF"
        brain_dispatch = "暂停自主任务，等待操作员确认"
        controller = "安全制动保持"
        gate = "BLOCKED"
    elif latest.event_type == "safety_stop":
        mode = "SAFETY_STOP"
        brain_dispatch = "保持停车，准备人工接管"
        controller = "安全制动保持"
        gate = "BLOCKED"
    elif fallback_id or latest.event_type.startswith("fallback") or status == "FALLBACK":
        mode = "RECOVERY"
        presentation = FALLBACK_PRESENTATION.get(
            fallback_id or "", SkillPresentation(latest.message, "恢复控制")
        )
        brain_dispatch = presentation.dispatch
        controller = presentation.controller
        gate = "CLEAR"
    else:
        mode = "NORMAL"
        presentation = SKILL_PRESENTATION.get(
            current_skill or "", SkillPresentation(latest.message, "任务状态保持")
        )
        brain_dispatch = presentation.dispatch
        controller = presentation.controller
        gate = "CLEAR"

    state = latest.state
    recent = [
        {
            "sequence": event.sequence,
            "sim_time_s": event.sim_time_s,
            "label": EVENT_LABELS.get(event.event_type, event.event_type),
            "message": event.message,
            "status": event.status,
        }
        for event in visible[-3:]
    ]
    collision = collision_summary or {}
    return {
        "run_id": latest.run_id,
        "scenario": latest.scenario,
        "sim_time_s": round(float(sim_time_s), 3),
        "goal": first.message,
        "status": status,
        "current_skill_id": current_skill,
        "fallback_id": fallback_id,
        "brain": {
            "mode": mode,
            "dispatch": brain_dispatch,
            "structured_intent": {
                "skill_id": current_skill,
                "fallback_id": fallback_id,
                "attempt": latest.evidence.get("attempt"),
            },
        },
        "cerebellum": {
            "controller": controller,
            "base_x_m": _state_value(state, "base_x_m"),
            "base_y_m": _state_value(state, "base_y_m"),
            "yaw_deg": _state_value(state, "yaw_deg"),
            "speed_mps": _state_value(state, "base_speed_mps"),
            "mast_height_m": _state_value(state, "mast_height_m"),
            "fork_tilt_deg": _state_value(state, "fork_tilt_deg"),
            "payload_attached": bool(state.get("payload_attached", False)),
            "payload_placed": bool(state.get("payload_placed", False)),
            "confidence": _state_value(latest.evidence, "confidence"),
        },
        "safety": {
            "gate": gate,
            "obstacle_visible": bool(state.get("obstacle_visible", False)),
            "stopped": bool(state.get("stopped", False)),
            "collision_guard": collision.get("collision_guard"),
            "collision_certified": collision.get("collision_certified"),
            "forbidden_collision_count": collision.get("forbidden_collision_count"),
            "minimum_body_clearance_m": collision.get("minimum_body_clearance_m"),
        },
        "audit": {
            "latest_sequence": latest.sequence,
            "event_type": latest.event_type,
            "recent": recent,
        },
    }


def build_ffmpeg_command(
    *,
    ffmpeg: str,
    source_video: Path,
    overlay_pattern: Path,
    fps: float,
    output_video: Path,
) -> list[str]:
    if fps <= 0 or not math.isfinite(fps):
        raise ValueError("fps must be positive and finite")
    fps_text = f"{fps:g}"
    filter_graph = (
        "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=2560:1080:0:180:color=0x07111D[base];"
        "[base][1:v]overlay=0:0:shortest=1[outv]"
    )
    return [
        ffmpeg,
        "-y",
        "-i",
        str(source_video),
        "-framerate",
        fps_text,
        "-i",
        str(overlay_pattern),
        "-filter_complex",
        filter_graph,
        "-map",
        "[outv]",
        "-r",
        fps_text,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output_video),
    ]


def _font_candidates(explicit: Path | None = None) -> list[Path]:
    values = [
        explicit,
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    return [value for value in values if value is not None and value.exists()]


def _select_cjk_font(explicit: Path | None = None) -> Path:
    candidates = _font_candidates(explicit)
    if not candidates:
        raise RuntimeError(
            "a CJK-capable font is required; pass scripts/build_split_presentation.py --font"
        )
    return candidates[0]


def _load_font(size: int, *, bold: bool = False, explicit: Path | None = None):
    from PIL import ImageFont

    return ImageFont.truetype(str(_select_cjk_font(explicit)), size=size, index=0)


def _fit_text(draw: Any, text: str, font: Any, width: int, max_lines: int = 2) -> list[str]:
    if not text:
        return ["—"]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
            if len(lines) == max_lines - 1:
                break
    if current and len(lines) < max_lines:
        consumed = sum(len(line) for line in lines) + len(current)
        if consumed < len(text) and len(current) > 1:
            current = current[:-1] + "…"
        lines.append(current)
    return lines


def _draw_text_lines(draw: Any, xy: tuple[int, int], lines: Sequence[str], font: Any, fill: str, spacing: int = 8) -> int:
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        box = draw.textbbox((x, y), line, font=font)
        y = box[3] + spacing
    return y


def render_overlay(
    snapshot: Mapping[str, Any],
    *,
    frame_index: int,
    frame_count: int,
    font_path: Path | None = None,
):
    """Render one transparent 2560x1080 presentation overlay."""

    from PIL import Image, ImageDraw

    image = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    navy = "#07111D"
    panel = "#0D1B2A"
    panel_alt = "#11263A"
    white = "#F2F7FA"
    muted = "#9EB3C5"
    cyan = "#3ED1E6"
    green = "#43D17C"
    amber = "#FFB547"
    red = "#FF5D68"
    mode = snapshot["brain"]["mode"]
    theme = presentation_theme(snapshot)
    accent = theme.accent

    draw.rectangle((0, 0, 1280, 180), fill=navy)
    draw.rectangle((0, 900, 1280, 1080), fill=navy)
    draw.rectangle((1280, 0, 2560, 1080), fill=theme.right_background)
    draw.rectangle((1276, 0, 1284, 1080), fill=accent)

    title_font = _load_font(44, bold=True, explicit=font_path)
    h1 = _load_font(36, bold=True, explicit=font_path)
    h2 = _load_font(theme.section_font_size, bold=True, explicit=font_path)
    dispatch_font = _load_font(
        theme.dispatch_font_size,
        bold=True,
        explicit=font_path,
    )
    body = _load_font(27, explicit=font_path)
    small = _load_font(21, explicit=font_path)
    mono = _load_font(23, explicit=font_path)

    source_title = str(snapshot.get("source_title", "ISAAC SIM · 仓库内部作业"))
    scene_label = str(snapshot.get("scene_label", "RAW PHYSICS VIEW"))
    draw.text((54, 34), source_title, font=title_font, fill=white)
    draw.text((54, 106), f"SCENE  {snapshot['scenario'].upper()}  ·  {scene_label}", font=small, fill=cyan)
    draw.text((54, 948), f"SIM TIME  {snapshot['sim_time_s']:06.2f}s", font=h1, fill=white)
    draw.text((402, 955), f"SKILL  {snapshot['current_skill_id'] or '—'}", font=h2, fill=muted)
    progress = 0.0 if frame_count <= 1 else min(1.0, frame_index / (frame_count - 1))
    draw.rounded_rectangle((54, 1024, 1218, 1044), radius=10, fill="#18344B")
    draw.rounded_rectangle((54, 1024, 54 + int(1164 * progress), 1044), radius=10, fill=accent)

    draw.text((1330, 32), "SEER-HVLA · BRAIN / CEREBELLUM", font=h1, fill=white)
    draw.text((1330, 86), "DECISION SUMMARY · 来自可审计事件", font=small, fill=cyan)
    status_color = theme.accent
    status_text = snapshot["status"]
    status_box = draw.textbbox((0, 0), status_text, font=h2)
    status_width = status_box[2] - status_box[0] + 44
    draw.rounded_rectangle((2510 - status_width, 32, 2510, 82), radius=14, fill=status_color)
    draw.text((2532 - status_width, 42), status_text, font=h2, fill=navy)

    def card(
        box: tuple[int, int, int, int],
        label: str,
        color: str = cyan,
        *,
        fill: str = panel,
    ):
        draw.rounded_rectangle(box, radius=18, fill=fill, outline="#355D79", width=2)
        draw.rectangle((box[0], box[1], box[0] + 8, box[3]), fill=color)
        draw.text((box[0] + 28, box[1] + 20), label, font=h2, fill=color)

    card((1320, 130, 2520, 285), "TASK / 任务目标")
    goal_lines = _fit_text(draw, str(snapshot["goal"]), body, 1120, max_lines=2)
    _draw_text_lines(draw, (1350, 184), goal_lines, body, white, 10)

    card(
        (1320, 310, 2520, 535),
        f"BRAIN / 大脑 · {theme.name} · 任务理解与技能分发",
        accent,
        fill=theme.card_fill,
    )
    draw.text((1350, 366), f"MODE   {mode}", font=mono, fill=accent)
    dispatch_lines = _fit_text(
        draw,
        str(snapshot["brain"]["dispatch"]),
        dispatch_font,
        1120,
        max_lines=2,
    )
    _draw_text_lines(draw, (1350, 410), dispatch_lines, dispatch_font, white, 8)
    intent = snapshot["brain"]["structured_intent"]
    draw.text((1350, 489), f"intent.skill={intent['skill_id'] or '—'}   fallback={intent['fallback_id'] or '—'}   attempt={intent['attempt'] or '—'}", font=small, fill=muted)

    card((1320, 560, 1920, 810), "CEREBELLUM / 小脑 · 规控执行", green)
    cerebellum = snapshot["cerebellum"]
    draw.text((1350, 616), str(cerebellum["controller"]), font=h1, fill=white)
    source_metrics = cerebellum.get("metrics")
    if source_metrics is not None:
        metrics = [f"{label:<13} {value}" for label, value in source_metrics]
    else:
        metrics = [
            f"base     x={cerebellum['base_x_m'] if cerebellum['base_x_m'] is not None else '—'} m  y={cerebellum['base_y_m'] if cerebellum['base_y_m'] is not None else '—'} m  yaw={cerebellum['yaw_deg'] if cerebellum['yaw_deg'] is not None else '—'}°",
            f"speed    {cerebellum['speed_mps'] if cerebellum['speed_mps'] is not None else '—'} m/s",
            f"mast     {cerebellum['mast_height_m'] if cerebellum['mast_height_m'] is not None else '—'} m",
            f"tilt     {cerebellum['fork_tilt_deg'] if cerebellum['fork_tilt_deg'] is not None else '—'} deg",
            f"payload  {'ATTACHED' if cerebellum['payload_attached'] else 'PLACED' if cerebellum['payload_placed'] else 'FREE'}",
        ]
    _draw_text_lines(draw, (1350, 674), metrics, mono, muted, 8)

    safety_color = red if snapshot["safety"]["gate"] == "BLOCKED" else green
    card((1945, 560, 2520, 810), "SAFETY / 安全门控", safety_color)
    safety = snapshot["safety"]
    draw.text((1975, 624), safety["gate"], font=title_font, fill=safety_color)
    source_details = safety.get("details")
    if source_details is not None:
        detail_lines = [f"{label:<10} {value}" for label, value in source_details]
        _draw_text_lines(draw, (1975, 692), detail_lines[:3], small, muted, 12)
    else:
        draw.text((1975, 692), f"obstacle  {'YES' if safety['obstacle_visible'] else 'NO'}", font=mono, fill=muted)
        draw.text((1975, 732), f"stopped   {'YES' if safety['stopped'] else 'NO'}", font=mono, fill=muted)
        geometry_state = (
            "CERTIFIED" if safety.get("collision_certified") is True else "UNRECORDED"
        )
        clearance = safety.get("minimum_body_clearance_m")
        clearance_text = f" · min {clearance:.3f}m" if isinstance(clearance, (int, float)) else ""
        draw.text((1975, 772), f"geometry  {geometry_state}{clearance_text}", font=small, fill=muted)

    card((1320, 835, 2520, 1045), "AUDIT / 最近审计事件", cyan)
    y = 890
    for event in snapshot["audit"]["recent"]:
        label = f"#{event['sequence']:02d}  {event['sim_time_s']:05.1f}s  {event['label']}"
        draw.text((1350, y), label, font=mono, fill=cyan if event is snapshot["audit"]["recent"][-1] else muted)
        message = _fit_text(draw, str(event["message"]), small, 720, max_lines=1)[0]
        draw.text((1765, y + 2), message, font=small, fill=white)
        y += 48
    return image


def render_overlay_frames(
    events: Sequence[Event],
    output_dir: Path,
    *,
    fps: float,
    frame_count: int,
    font_path: Path | None = None,
    collision_summary: Mapping[str, Any] | None = None,
) -> Path:
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    output_dir.mkdir(parents=True, exist_ok=False)
    event_times = presentation_event_times(events, fps)
    clocked_events = [
        replace(event, sim_time_s=event_times[index])
        for index, event in enumerate(events)
    ]
    for frame_index in range(frame_count):
        sim_time = frame_time_s(frame_index, fps)
        snapshot = decision_snapshot(
            clocked_events,
            sim_time,
            collision_summary=collision_summary,
        )
        image = render_overlay(
            snapshot,
            frame_index=frame_index,
            frame_count=frame_count,
            font_path=font_path,
        )
        image.save(output_dir / f"frame-{frame_index:06d}.png", optimize=True)
    return output_dir / "frame-%06d.png"
