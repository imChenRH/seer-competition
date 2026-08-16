"""Run and validate a sanitized official LIBERO task-8 Fast-WAM preflight."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping

from .rollout import (
    CANONICAL_POLICY_PROMPT,
    load_policy_on_cuda,
    validate_policy_action,
)


def validate_preflight_record(record: Mapping[str, Any]) -> dict[str, Any]:
    validated = deepcopy(dict(record))
    if validated.get("schema_version") != "1.0":
        raise ValueError("unsupported Fast-WAM preflight schema")
    expected_task = {
        "task_suite": "libero_goal",
        "task_id": 8,
        "task_name": "put_the_bowl_on_the_plate",
        "task_description": CANONICAL_POLICY_PROMPT,
    }
    for key, expected in expected_task.items():
        if validated.get(key) != expected:
            raise ValueError(f"Fast-WAM preflight {key} does not match task 8")
    shapes = validated.get("observation_shapes")
    if not isinstance(shapes, dict) or shapes != {
        "image": [224, 224, 3],
        "image2": [224, 224, 3],
    }:
        raise ValueError("Fast-WAM preflight must bind both 224px RGB cameras")
    validated["action"] = list(validate_policy_action(validated.get("action", [])))
    versions = validated.get("versions")
    if not isinstance(versions, dict) or set(versions) != {"lerobot", "mujoco", "torch"}:
        raise ValueError("Fast-WAM preflight versions are incomplete")
    if not all(isinstance(value, str) and value for value in versions.values()):
        raise ValueError("Fast-WAM preflight versions must be non-empty strings")
    if not isinstance(validated.get("cuda_device"), str) or not validated["cuda_device"]:
        raise ValueError("Fast-WAM preflight CUDA device is missing")
    elapsed = validated.get("elapsed_s")
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
        raise ValueError("Fast-WAM preflight elapsed time must be numeric")
    if not math.isfinite(float(elapsed)) or float(elapsed) <= 0:
        raise ValueError("Fast-WAM preflight elapsed time must be positive")
    return validated


def run_preflight(model_dir: Path) -> dict[str, Any]:
    import lerobot
    import mujoco
    import torch
    from libero.libero import benchmark
    from lerobot.envs.configs import LiberoEnv as LiberoEnvConfig
    from lerobot.envs.libero import LiberoEnv
    from lerobot.envs.utils import preprocess_observation
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.fastwam.configuration_fastwam import FastWAMConfig
    from lerobot.policies.fastwam.modeling_fastwam import FastWAMPolicy

    started = time.perf_counter()
    suite = benchmark.get_benchmark_dict()["libero_goal"]()
    task = suite.get_task(8)
    env = LiberoEnv(
        task_suite=suite,
        task_id=8,
        task_suite_name="libero_goal",
        episode_length=300,
        camera_name="agentview_image,robot0_eye_in_hand_image",
        obs_type="pixels_agent_pos",
        observation_width=224,
        observation_height=224,
        init_states=True,
        episode_index=0,
        n_envs=1,
        num_steps_wait=10,
        control_freq=20,
        control_mode="relative",
        hard_reset=True,
    )
    try:
        observation, _ = env.reset(seed=202608160)
        shapes = {
            name: list(observation["pixels"][name].shape)
            for name in ("image", "image2")
        }
        config, policy = load_policy_on_cuda(
            model_dir, FastWAMConfig, FastWAMPolicy, torch
        )
        policy.eval()
        preprocessor, postprocessor = make_pre_post_processors(
            policy_cfg=config,
            pretrained_path=str(model_dir),
            preprocessor_overrides={"device_processor": {"device": "cuda"}},
        )
        env_config = LiberoEnvConfig(
            task="libero_goal",
            task_ids=[8],
            fps=20,
            observation_height=224,
            observation_width=224,
        )
        env_preprocessor, _ = env_config.get_env_processors()
        policy_observation = preprocess_observation(observation)
        policy_observation["task"] = [CANONICAL_POLICY_PROMPT]
        policy_observation = env_preprocessor(policy_observation)
        policy_observation = preprocessor(policy_observation)
        with torch.inference_mode():
            action_tensor = policy.select_action(policy_observation)
        action_tensor = postprocessor(action_tensor)
        if action_tensor.ndim == 2 and action_tensor.shape[0] == 1:
            action_tensor = action_tensor[0]
        action = list(
            validate_policy_action(action_tensor.detach().to("cpu").reshape(-1).tolist())
        )
        torch.cuda.synchronize()
    finally:
        env.close()
    return validate_preflight_record(
        {
            "schema_version": "1.0",
            "task_suite": "libero_goal",
            "task_id": 8,
            "task_name": task.name,
            "task_description": task.language,
            "observation_shapes": shapes,
            "action": action,
            "versions": {
                "lerobot": lerobot.__version__,
                "mujoco": mujoco.__version__,
                "torch": torch.__version__,
            },
            "cuda_device": torch.cuda.get_device_name(0),
            "elapsed_s": round(time.perf_counter() - started, 3),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight official LIBERO task 8 with Fast-WAM")
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    record = run_preflight(args.model_dir)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
