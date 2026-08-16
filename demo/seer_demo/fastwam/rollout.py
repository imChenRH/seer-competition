"""Run Fast-WAM against the custom LIBERO apple/plate visual variant."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Iterable, Mapping

from ..contracts import EventWriter, load_events
from .contracts import (
    ACTION_SCHEMA_VERSION,
    ActionRecord,
    FASTWAM_SCENARIO,
    FASTWAM_SKILLS,
    load_action_records,
    validate_fastwam_package,
)
from .scene_variant import ApplePlateLiberoEnv, SCENE_VARIANT_ID


CANONICAL_POLICY_PROMPT = "Put the bowl on the plate"
AGENTOS_TASK = "把红色苹果放入黄色盘子"
POLICY_CHECKPOINT_NAME = "fastwam_libero_uncond_2cam224"


def validate_policy_action(action: Iterable[object]) -> tuple[float, ...]:
    try:
        values = tuple(action)
    except TypeError as exc:
        raise ValueError("Fast-WAM action must be iterable") from exc
    if len(values) != 7:
        raise ValueError("Fast-WAM action must contain exactly seven values")
    normalized = []
    for value in values:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Fast-WAM action components must be numeric")
        number = float(value)
        if not math.isfinite(number) or not -1.0 <= number <= 1.0:
            raise ValueError("Fast-WAM action components must be finite and bounded")
        normalized.append(number)
    return tuple(normalized)


def load_policy_on_cuda(
    model_dir: Path,
    config_class: Any,
    policy_class: Any,
    torch_module: Any,
) -> tuple[Any, Any]:
    """Load the checkpoint once on CPU, then make one bounded CUDA move."""
    config = config_class.from_pretrained(str(model_dir))
    config.device = "cpu"
    config.n_action_steps = 10
    policy = policy_class.from_pretrained(str(model_dir), config=config)
    policy.to("cuda")
    config.device = "cuda"
    policy.model.device = torch_module.device("cuda")
    return config, policy


def batch_single_robot_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Add the vector-env batch axis expected by LeRobot's LIBERO processor."""

    def batch_nested(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: batch_nested(item) for key, item in value.items()}
        if hasattr(value, "ndim") and hasattr(value, "__getitem__"):
            return value[None, ...]
        return value

    prepared = dict(observation)
    robot_state = observation.get("robot_state")
    if isinstance(robot_state, Mapping):
        prepared["robot_state"] = batch_nested(robot_state)
    return prepared


def precompute_task_context(
    config: Any,
    torch_module: Any,
    encoder_loader: Any,
    tokenizer_builder: Any,
    task: str,
) -> tuple[Any, Any]:
    """Encode the reference prompt once, then release the resident text encoder."""
    prompt = config.prompt_template.format(task=task)
    encoder = encoder_loader(
        model_id=config.text_encoder_model_id,
        torch_dtype=torch_module.bfloat16,
        device="cuda",
    )
    tokenizer = tokenizer_builder(
        model_id=config.tokenizer_model_id,
        tokenizer_max_len=config.tokenizer_max_len,
    )
    input_ids, context_mask = tokenizer(
        prompt, return_mask=True, add_special_tokens=True
    )
    input_ids = input_ids.to("cuda")
    context_mask = context_mask.to("cuda", dtype=torch_module.bool)
    with torch_module.inference_mode():
        context = encoder(input_ids, context_mask)
    context[~context_mask] = 0.0
    context_mask = torch_module.ones_like(context_mask, dtype=torch_module.bool)
    expected = (1, config.context_len, config.video_dit_config["text_dim"])
    if tuple(context.shape) != expected or tuple(context_mask.shape) != expected[:2]:
        raise RuntimeError("precomputed Fast-WAM context has an unexpected shape")
    context = context.detach().to("cpu")
    context_mask = context_mask.detach().to("cpu")
    del encoder, tokenizer, input_ids
    gc.collect()
    torch_module.cuda.empty_cache()
    return context, context_mask


def derive_phase(observation: Mapping[str, Any]) -> str:
    if observation.get("official_success") is True:
        return "ARM-VER-01"
    error = float(observation.get("plate_xy_error_m", math.inf))
    lift = float(observation.get("apple_lift_m", 0.0))
    closed = observation.get("gripper_closed") is True
    if closed and lift >= 0.025 and error <= 0.08:
        return "ARM-OP-04"
    if closed and lift >= 0.025:
        return "ARM-OP-03"
    if closed:
        return "ARM-OP-02"
    return "ARM-OP-01"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_actions(path: Path, records: list[ActionRecord]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(
                json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )


def _encode_video(frames_dir: Path, output_path: Path, fps: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to encode the Fast-WAM recording")
    process = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%05d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=900,
    )
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {process.stderr[-1000:]}")


def _event_frame_for_skill(states: list[dict[str, Any]], skill_id: str) -> int:
    if skill_id in {"ARM-PER-01", "ARM-PLAN-01"}:
        return 0
    if skill_id == "WAM-ACT-01":
        return min(1, len(states) - 1)
    target_phase = skill_id
    for index, state in enumerate(states):
        if derive_phase(state) == target_phase:
            return index
    return len(states) - 1


def _write_selected_events(
    path: Path,
    run_id: str,
    states: list[dict[str, Any]],
    fps: int,
    success: bool,
) -> None:
    terminal_frame = len(states) - 1
    with EventWriter(path, run_id, FASTWAM_SCENARIO, "fastwam_policy") as writer:
        writer.emit(
            "task_started",
            0.0,
            status="RUNNING",
            message=AGENTOS_TASK,
            state={"policy_prompt": CANONICAL_POLICY_PROMPT},
            evidence={"observed_frame": 0, "scene_variant": SCENE_VARIANT_ID},
        )
        if success:
            for skill_id in FASTWAM_SKILLS:
                frame = _event_frame_for_skill(states, skill_id)
                state = dict(states[frame])
                writer.emit(
                    "skill_started",
                    frame / fps,
                    status="RUNNING",
                    skill_id=skill_id,
                    evidence={"observed_frame": frame},
                )
                writer.emit(
                    "skill_completed",
                    frame / fps,
                    status="RUNNING",
                    skill_id=skill_id,
                    state=state,
                    evidence={"observed_frame": frame, "measured": True},
                )
            writer.emit(
                "task_completed",
                terminal_frame / fps,
                status="COMPLETED",
                state={**states[-1], "official_success": True},
                evidence={"observed_frame": terminal_frame, "predicate": "env.check_success"},
            )
        else:
            for skill_id in FASTWAM_SKILLS[:3]:
                frame = _event_frame_for_skill(states, skill_id)
                writer.emit(
                    "skill_started",
                    frame / fps,
                    status="RUNNING",
                    skill_id=skill_id,
                    evidence={"observed_frame": frame},
                )
                writer.emit(
                    "skill_completed",
                    frame / fps,
                    status="RUNNING",
                    skill_id=skill_id,
                    state=states[frame],
                    evidence={"observed_frame": frame, "measured": True},
                )
            writer.emit(
                "skill_started",
                min(1, terminal_frame) / fps,
                status="RUNNING",
                skill_id="ARM-OP-01",
                evidence={"observed_frame": min(1, terminal_frame)},
            )
            writer.emit(
                "task_failed",
                terminal_frame / fps,
                status="FAILED",
                state={**states[-1], "official_success": False},
                evidence={"observed_frame": terminal_frame, "predicate": "env.check_success"},
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a truthful Fast-WAM apple/plate rollout")
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--max-steps", type=int, default=300)
    return parser


def run_remote_rollout(args: argparse.Namespace) -> dict[str, object]:
    import numpy as np
    from PIL import Image
    import torch
    from lerobot.envs.configs import LiberoEnv as LiberoEnvConfig
    from lerobot.envs.utils import preprocess_observation
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.fastwam.configuration_fastwam import FastWAMConfig
    from lerobot.policies.fastwam.modeling_fastwam import FastWAMPolicy
    from lerobot.policies.fastwam.wan.components import (
        build_wan_tokenizer,
        load_pretrained_wan_text_encoder,
    )

    if args.attempts != 5:
        raise ValueError("formal Fast-WAM evaluation requires exactly five attempts")
    if args.fps != 20 or args.width < 640 or args.height < 360 or args.max_steps <= 0:
        raise ValueError("invalid recording clock, resolution, or step budget")
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=False)
    attempts_dir = output_dir / "attempts"
    attempts_dir.mkdir()

    context_config = FastWAMConfig.from_pretrained(str(args.model_dir))
    task_context, task_context_mask = precompute_task_context(
        context_config,
        torch,
        load_pretrained_wan_text_encoder,
        build_wan_tokenizer,
        CANONICAL_POLICY_PROMPT,
    )
    config, policy = load_policy_on_cuda(
        args.model_dir, FastWAMConfig, FastWAMPolicy, torch
    )
    policy.eval()
    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=config,
        pretrained_path=str(args.model_dir),
        preprocessor_overrides={"device_processor": {"device": "cuda"}},
    )
    env_config = LiberoEnvConfig(
        task="libero_goal",
        task_ids=[8],
        fps=args.fps,
        observation_height=224,
        observation_width=224,
    )
    env_preprocessor, _ = env_config.get_env_processors()

    attempt_results: list[dict[str, object]] = []
    captured: list[dict[str, object]] = []
    for attempt_index in range(args.attempts):
        seed = 202608160 + attempt_index
        attempt_dir = attempts_dir / f"attempt-{attempt_index}"
        attempt_dir.mkdir()
        frames_dir = attempt_dir / "frames"
        frames_dir.mkdir()
        env = ApplePlateLiberoEnv(attempt_index)
        policy.reset()
        actions: list[ActionRecord] = []
        states: list[dict[str, Any]] = []
        success = False
        terminal_reason = "step_budget"
        try:
            observation, _ = env.reset(seed)
            initial_state = env.physical_state(observation, official_success=False)
            states.append(initial_state)
            Image.fromarray(env.render_frame(args.width, args.height)).save(
                frames_dir / "frame_00000.png"
            )
            for step in range(args.max_steps):
                model_call = len(policy._action_queue) == 0
                policy_observation = preprocess_observation(
                    batch_single_robot_state(observation)
                )
                policy_observation = env_preprocessor(policy_observation)
                policy_observation = preprocessor(policy_observation)
                policy_observation["context"] = task_context
                policy_observation["context_mask"] = task_context_mask
                started = time.perf_counter()
                with torch.inference_mode():
                    action_tensor = policy.select_action(policy_observation)
                action_tensor = postprocessor(action_tensor)
                if action_tensor.ndim == 2 and action_tensor.shape[0] == 1:
                    action_tensor = action_tensor[0]
                values = validate_policy_action(
                    action_tensor.detach().to("cpu").reshape(-1).tolist()
                )
                latency = time.perf_counter() - started
                observation, _, terminated, truncated, info = env.step(
                    np.asarray(values, dtype=np.float32)
                )
                official_success = bool(info.get("is_success", False))
                state = env.physical_state(
                    observation, official_success=official_success
                )
                states.append(state)
                frame = step + 1
                Image.fromarray(env.render_frame(args.width, args.height)).save(
                    frames_dir / f"frame_{frame:05d}.png"
                )
                actions.append(
                    ActionRecord(
                        ACTION_SCHEMA_VERSION,
                        args.run_id,
                        step,
                        frame,
                        frame / args.fps,
                        values,
                        model_call,
                        round(latency, 6),
                    )
                )
                if official_success:
                    success = True
                    terminal_reason = "official_success"
                    break
                if terminated or truncated:
                    terminal_reason = "environment_terminated"
                    break
        except Exception as exc:
            terminal_reason = f"policy_or_environment_error:{type(exc).__name__}"
            _write_json(
                attempt_dir / "error.json",
                {"type": type(exc).__name__, "message": str(exc)[:500]},
            )
        finally:
            env.close()
        _write_actions(attempt_dir / "actions.jsonl", actions)
        _write_json(attempt_dir / "states.json", states)
        _encode_video(frames_dir, attempt_dir / "simulation.mp4", args.fps)
        shutil.rmtree(frames_dir)
        policy_calls = sum(action.model_call for action in actions)
        result = {
            "attempt_index": attempt_index,
            "seed": seed,
            "init_state_id": attempt_index,
            "success": success,
            "executed_steps": len(actions),
            "policy_calls": policy_calls,
            "terminal_reason": terminal_reason,
        }
        attempt_results.append(result)
        captured.append(
            {"dir": attempt_dir, "actions": actions, "states": states, "result": result}
        )

    successful = [item for item in captured if item["result"]["success"]]
    selected_attempt = int(successful[0]["result"]["attempt_index"]) if successful else None
    presented = successful[0] if successful else captured[0]
    selected_actions = list(presented["actions"])
    selected_states = list(presented["states"])
    if not selected_actions or not selected_states:
        raise RuntimeError("presented Fast-WAM attempt has no recorded evidence")
    shutil.copy2(presented["dir"] / "simulation.mp4", output_dir / "simulation.mp4")
    shutil.copy2(presented["dir"] / "actions.jsonl", output_dir / "actions.jsonl")
    _write_json(output_dir / "evaluation.json", {"attempts": attempt_results})
    scene = {
        "schema_version": "1.0",
        "scene_variant": SCENE_VARIANT_ID,
        "official_suite": "libero_goal",
        "official_task_id": 8,
        "official_task_name": "put_the_bowl_on_the_plate",
        "agentos_task": AGENTOS_TASK,
        "policy_prompt": CANONICAL_POLICY_PROMPT,
        "semantic_adapter": {"akita_black_bowl": "red_apple", "plate": "yellow_plate"},
        "apple_specific_finetuning": False,
    }
    _write_json(output_dir / "scene_variant.json", scene)
    _write_selected_events(
        output_dir / "events.jsonl",
        args.run_id,
        selected_states,
        args.fps,
        selected_attempt is not None,
    )
    events = load_events(output_dir / "events.jsonl")
    validation = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "scenario": FASTWAM_SCENARIO,
        "source": "fastwam_policy",
        "event_count": len(events),
        "terminal_status": "COMPLETED" if selected_attempt is not None else "FAILED",
        "duration_s": events[-1].sim_time_s,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_file": "events.jsonl",
        "actions_file": "actions.jsonl",
        "video_file": "simulation.mp4",
        "scene_file": "scene_variant.json",
        "resolution": f"{args.width}x{args.height}",
        "fps": args.fps,
        "frame_count": len(selected_states),
        "action_count": len(selected_actions),
        "policy_call_count": sum(action.model_call for action in selected_actions),
        "policy_checkpoint": POLICY_CHECKPOINT_NAME,
        "policy_prompt": CANONICAL_POLICY_PROMPT,
        "agentos_task": AGENTOS_TASK,
        "scene_variant": SCENE_VARIANT_ID,
        "official_success": selected_attempt is not None,
        "attempt_count": len(attempt_results),
        "attempts": attempt_results,
        "selected_attempt": selected_attempt,
        "presented_attempt": int(presented["result"]["attempt_index"]),
        "additional_evidence_files": ["actions.jsonl", "evaluation.json"],
        "claim_boundary": (
            "记录仅证明官方 Fast-WAM checkpoint 在一次自定义 LIBERO 视觉语义变体中的五次固定初态结果；"
            "不证明苹果专项训练、实机迁移或生产安全。"
        ),
    }
    validate_fastwam_package(validation, events, load_action_records(output_dir / "actions.jsonl"))
    _write_json(output_dir / "summary.json", validation)
    return validation


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_remote_rollout(args)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
