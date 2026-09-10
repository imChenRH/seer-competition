"""Fail-closed adapter for canonical LIBERO bowl-on-plate task 8."""

from __future__ import annotations

import math
from typing import Any


SCENE_VARIANT_ID = "libero_goal_8_bowl_plate_canonical_v1"
CANONICAL_TASK_ID = 8
CANONICAL_SUITE = "libero_goal"
CANONICAL_BOWL_BODY = "akita_black_bowl_1"
CANONICAL_PLATE_BODY = "plate_1"


class BowlPlateLiberoEnv:
    """Composition wrapper that preserves the official task BDDL and assets."""

    def __init__(
        self,
        init_state_id: int,
        *,
        observation_size: int = 224,
        episode_length: int = 300,
    ):
        if type(init_state_id) is not int or init_state_id < 0:
            raise ValueError("init_state_id must be a non-negative integer")
        if type(episode_length) is not int or episode_length <= 0:
            raise ValueError("episode_length must be a positive integer")
        from libero.libero import benchmark
        from lerobot.envs.libero import LiberoEnv

        suite = benchmark.get_benchmark_dict()[CANONICAL_SUITE]()
        task = suite.get_task(CANONICAL_TASK_ID)
        if task.name != "put_the_bowl_on_the_plate":
            raise RuntimeError("LIBERO task-id map no longer matches the validated task")
        self._env = LiberoEnv(
            task_suite=suite,
            task_id=CANONICAL_TASK_ID,
            task_suite_name=CANONICAL_SUITE,
            episode_length=episode_length,
            camera_name="agentview_image,robot0_eye_in_hand_image",
            obs_type="pixels_agent_pos",
            observation_width=observation_size,
            observation_height=observation_size,
            init_states=True,
            episode_index=init_state_id,
            n_envs=1,
            num_steps_wait=10,
            control_freq=20,
            control_mode="relative",
            hard_reset=True,
        )
        self._initial_bowl_z: float | None = None

    @property
    def task_description(self) -> str:
        return self._env.task_description

    def reset(self, seed: int):
        observation, info = self._env.reset(seed=seed)
        bowl = self._body_position(CANONICAL_BOWL_BODY)
        self._body_position(CANONICAL_PLATE_BODY)
        self._initial_bowl_z = bowl[2]
        return observation, info

    def step(self, action):
        return self._env.step(action)

    def close(self) -> None:
        self._env.close()

    def render_frame(self, width: int, height: int):
        if self._env._env is None:
            raise RuntimeError("environment must be reset before rendering")
        sim = self._env._env.env.sim
        frame = sim.render(width=width, height=height, camera_name="agentview")
        return frame[::-1, ::-1].copy()

    def physical_state(self, observation: dict[str, Any], *, official_success: bool) -> dict[str, Any]:
        bowl = self._body_position(CANONICAL_BOWL_BODY)
        plate = self._body_position(CANONICAL_PLATE_BODY)
        gripper = observation.get("robot_state", {}).get("gripper", {}).get("qpos")
        gripper_values = [] if gripper is None else [float(value) for value in gripper]
        initial_z = bowl[2] if self._initial_bowl_z is None else self._initial_bowl_z
        return {
            "bowl_x_m": round(bowl[0], 6),
            "bowl_y_m": round(bowl[1], 6),
            "bowl_z_m": round(bowl[2], 6),
            "bowl_lift_m": round(max(0.0, bowl[2] - initial_z), 6),
            "plate_x_m": round(plate[0], 6),
            "plate_y_m": round(plate[1], 6),
            "plate_z_m": round(plate[2], 6),
            "plate_xy_error_m": round(math.hypot(bowl[0] - plate[0], bowl[1] - plate[1]), 6),
            "gripper_qpos": [round(value, 6) for value in gripper_values],
            "gripper_closed": bool(gripper_values and max(abs(value) for value in gripper_values) < 0.025),
            "official_success": bool(official_success),
        }

    def _body_position(self, token: str) -> tuple[float, float, float]:
        if self._env._env is None:
            raise RuntimeError("environment must be reset before reading bodies")
        sim = self._env._env.env.sim
        model = sim.model
        candidates = (token, f"{token}_main", f"{token}_root", f"{token}_object")
        for candidate in candidates:
            try:
                body_id = model.body_name2id(candidate)
                values = sim.data.body_xpos[body_id]
                return tuple(float(value) for value in values)
            except (KeyError, ValueError):
                continue
        for body_id in range(model.nbody):
            try:
                name = model.body_id2name(body_id)
            except AttributeError:
                name = None
            if name and token in name:
                values = sim.data.body_xpos[body_id]
                return tuple(float(value) for value in values)
        raise RuntimeError(f"MuJoCo body for {token} was not created")
