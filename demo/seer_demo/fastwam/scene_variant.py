"""LIBERO task-8 visual and semantic adapter for the apple/plate demo."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any


ASSETS = Path(__file__).with_name("assets")
SCENE_VARIANT_ID = "libero_goal_8_apple_plate_visual_v1"
CANONICAL_TASK_ID = 8
CANONICAL_SUITE = "libero_goal"


def register_scene_objects() -> None:
    """Register the two primitive objects without importing LIBERO on macOS."""
    from libero.libero.envs.base_object import OBJECTS_DICT, register_object
    from robosuite.models.objects import MujocoXMLObject

    def initialize(instance: Any, asset_name: str, name: str) -> None:
        MujocoXMLObject.__init__(
            instance,
            str(ASSETS / asset_name),
            name=name,
            joints=[dict(type="free", damping="0.0005")],
            obj_type="all",
            duplicate_collision_geoms=False,
        )
        instance.category_name = name
        instance.rotation = (0.0, 0.0)
        instance.rotation_axis = "x"
        instance.object_properties = {"vis_site_names": {}}

    if "red_apple" not in OBJECTS_DICT:
        @register_object
        class RedApple(MujocoXMLObject):
            def __init__(self, name: str = "red_apple"):
                initialize(self, "red_apple.xml", name)

    if "yellow_plate" not in OBJECTS_DICT:
        @register_object
        class YellowPlate(MujocoXMLObject):
            def __init__(self, name: str = "yellow_plate"):
                initialize(self, "yellow_plate.xml", name)


class ApplePlateLiberoEnv:
    """Composition wrapper that swaps only the official task-8 BDDL before reset."""

    def __init__(self, init_state_id: int, *, observation_size: int = 224):
        if type(init_state_id) is not int or init_state_id < 0:
            raise ValueError("init_state_id must be a non-negative integer")
        register_scene_objects()
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
            episode_length=300,
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
        self._env._task_bddl_file = str(
            ASSETS / "put_red_apple_on_yellow_plate.bddl"
        )
        self._env.task_description = "Put the bowl on the plate"
        self._initial_apple_z: float | None = None

    @property
    def task_description(self) -> str:
        return self._env.task_description

    def reset(self, seed: int):
        observation, info = self._env.reset(seed=seed)
        apple = self._body_position("red_apple_1")
        self._initial_apple_z = apple[2]
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
        apple = self._body_position("red_apple_1")
        plate = self._body_position("yellow_plate_1")
        gripper = observation.get("robot_state", {}).get("gripper", {}).get("qpos")
        gripper_values = [] if gripper is None else [float(value) for value in gripper]
        initial_z = apple[2] if self._initial_apple_z is None else self._initial_apple_z
        return {
            "apple_x_m": round(apple[0], 6),
            "apple_y_m": round(apple[1], 6),
            "apple_z_m": round(apple[2], 6),
            "apple_lift_m": round(max(0.0, apple[2] - initial_z), 6),
            "plate_x_m": round(plate[0], 6),
            "plate_y_m": round(plate[1], 6),
            "plate_z_m": round(plate[2], 6),
            "plate_xy_error_m": round(math.hypot(apple[0] - plate[0], apple[1] - plate[1]), 6),
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
