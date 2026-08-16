# Fast-WAM Red Apple to Yellow Plate Demo Design

## Decision

Build a second, independent manipulation evidence track around the official Fast-WAM LIBERO checkpoint. The task is a visual and semantic adapter of the official LIBERO Goal task `put_the_bowl_on_the_plate` (suite `libero_goal`, task id `8`): a registered red-apple object replaces the bowl, a yellow-plate object replaces the plate, and the official success predicate remains an `On(object, plate)` relationship.

This route is preferred over a rule-controlled Isaac animation because Fast-WAM must generate the executed 7-D actions. It is preferred over RoboTwin because the available server already contains the 12 GB LIBERO 7-D checkpoint, while RoboTwin requires a separate 14-D checkpoint, dual-arm environment, and a much larger asset installation.

## Goal

Produce a verifiable Demo in which:

1. the operator task is “把红色苹果放入黄色盘子”;
2. AgentOS maps the natural-language object labels to the canonical manipulation roles `graspable object` and `target plate`;
3. Fast-WAM receives the canonical task prompt and two real camera observations, then generates 7-D end-effector and gripper actions;
4. LIBERO/MuJoCo executes those actions without a rule controller substituting for the policy;
5. success is recorded only when LIBERO's task predicate reports the apple is on the plate;
6. the web console replays the same video clock alongside structured brain/cerebellum dispatch and action evidence.

## Truth Boundary

The Demo may claim:

- the released Fast-WAM LIBERO checkpoint was loaded on the RTX 4090;
- the policy produced the action chunks executed by LIBERO/MuJoCo;
- the recorded rollout passed or failed the official task predicate;
- the red apple and yellow plate are a custom visual/semantic variant of a known LIBERO bowl-on-plate task;
- measured inference latency applies only to the recorded run and server configuration.

The Demo must not claim:

- Fast-WAM was fine-tuned specifically on apples or yellow plates;
- the custom variant reproduces the paper's benchmark score;
- the rollout proves real-robot transfer, collision-safe force control, or production safety;
- hidden model reasoning or chain-of-thought is being displayed;
- a failed rollout succeeded because a rule controller completed the motion.

## Upstream Basis

- LeRobot's official Fast-WAM guide exposes `lerobot/fastwam_libero_uncond_2cam224`, a 7-D LIBERO policy, and the official `lerobot-eval` recipe: <https://github.com/huggingface/lerobot/blob/main/docs/source/policy_fastwam_README.md>.
- LeRobot's official LIBERO wrapper defines a 7-D action as 6-D end-effector delta plus one gripper value and supports `gym_kwargs.task_ids` to restrict a suite to one task: <https://github.com/huggingface/lerobot/blob/main/src/lerobot/envs/libero.py>.
- The official LIBERO task map identifies `put_the_bowl_on_the_plate` as `libero_goal` task id `8`: <https://github.com/Lifelong-Robot-Learning/LIBERO/blob/master/libero/libero/benchmark/libero_suite_task_map.py>.
- The official BDDL goal is `On(akita_black_bowl_1, plate_1)`: <https://github.com/Lifelong-Robot-Learning/LIBERO/blob/master/libero/libero/bddl_files/libero_goal/put_the_bowl_on_the_plate.bddl>.

## Architecture

```text
Operator instruction
        |
        v
AgentOS semantic adapter
red apple -> graspable object
yellow plate -> target plate
        |
        v
Canonical LIBERO task contract
put object on plate / task id 8
        |
        v
Fast-WAM policy on RTX 4090
two RGB cameras + proprioception -> 7-D action chunks
        |
        v
LIBERO / MuJoCo execution
        |
        +--> raw scene video
        +--> action JSONL and inference timings
        +--> physical state observations
        +--> official success predicate
        |
        v
Validated evidence package -> split presentation -> local read-only console
```

The existing forklift engine remains unchanged. The manipulation track uses a separate module and validator so that forklift-specific collision, skill, and terminal contracts cannot accidentally certify a Fast-WAM rollout.

## Scene Variant

The run overlay contains two registered LIBERO objects:

- `RedApple`: a dynamic MuJoCo XML object with a red spherical collision/visual body, a shallow top dimple, and a short dark stem; its free joint and bounding sites follow the requirements of `MujocoXMLObject`.
- `YellowPlate`: the standard LIBERO plate geometry with its material overridden to industrial yellow while preserving the plate collision mesh.

A copied BDDL file changes only the language, object types, object-of-interest declarations, initial region bindings, and goal identifiers. Fixture layout, robot, controller, plate region, apple region, and the `On` goal topology remain aligned with the official task.

AgentOS records the semantic mapping explicitly. The policy prompt remains the exact canonical “Put the bowl on the plate” instruction used by the official task; the UI must not imply that the checkpoint was trained on the Chinese instruction or apple-specific language.

## Rollout and Selection Rules

- Environment: Linux, headless EGL, MuJoCo `3.8.1` resolved by LeRobot's official `hf-libero` extra, LeRobot `0.6.2`, RTX 4090.
- Checkpoint: existing local `/root/autodl-tmp/models/fastwam_libero_uncond_2cam224`; no second 12 GB download.
- Policy inputs: agent view, wrist view, and real proprioceptive state from the environment.
- Action contract: shape `[7]`, values finite and within the declared action bounds after post-processing.
- Action chunk execution: ten policy actions per replanning window, matching the official reproduction recipe.
- Evaluation set: five fixed LIBERO initialization states in deterministic order. Every attempt is retained in the evaluation summary.
- Publication rule: the presentation may use the first successful fixed attempt, but the summary must report all five outcomes and identify the selected attempt. If all five fail, publish a failure analysis rather than a fabricated success video.
- Terminal rule: only `env.check_success()` can produce `COMPLETED`; timeout, non-finite action, model error, or missing evidence produces `FAILED`.

## Evidence Contract

The formal run directory is `demo/evidence/fastwam-apple-plate-20260816-v1-r4/` and contains the following files. The executed semantic-transfer budget is 600 steps per fixed seed; this is explicitly not the official 300-step benchmark budget:

- `events.jsonl`: contiguous structured events tied to observed video frames;
- `actions.jsonl`: one record per executed action with step, chunk index, seven finite values, model-call flag, and measured latency;
- `summary.json`: environment, checkpoint, exact task, seed/init-state results, selected attempt, official terminal predicate, video metadata, and claim boundary;
- `scene_variant.json`: hashes and semantic description of the BDDL/object overlay;
- `simulation.mp4`: raw rollout video with the complete workspace and robot visible;
- `presentation.mp4`: 2560x1080 synchronized split view;
- `run.log`: sanitized runtime log without credentials or model-cache paths that reveal secrets.

The validator fails closed on sequence gaps, source or run-id changes, non-monotonic frames, malformed actions, absent checkpoint identity, mismatched attempt statistics, video clock disagreement, or a success event without the official success observation.

## Structured Skill Timeline

The right panel uses observable phases, not hidden reasoning:

1. `ARM-PER-01` — scene and task-role binding recorded;
2. `ARM-PLAN-01` — AgentOS dispatches the canonical object-to-plate skill;
3. `WAM-ACT-01` — Fast-WAM begins 7-D action generation;
4. `ARM-OP-01` — end effector approaches the apple;
5. `ARM-OP-02` — apple grasp is physically observed;
6. `ARM-OP-03` — apple lift and transfer are observed;
7. `ARM-OP-04` — apple is lowered onto the plate and released;
8. `ARM-VER-01` — LIBERO success predicate is checked.

Phase transitions are derived from simulator state, gripper/object relation, object height, distance to the plate, and the official terminal predicate. They are not inferred from latency or from an animation schedule.

## Presentation and Web Console

The Fast-WAM tab becomes a full evidence view after task dispatch:

- left: synchronized raw manipulation video;
- right: current AgentOS mapping, active Fast-WAM action chunk, seven action values, policy-call latency, physical phase, and official success state;
- lower cards: attempt statistics, checkpoint/environment identity, evidence hashes, and claim boundary;
- colors: blue for planning/approach, amber for grasp/transfer, green only after official success, red for failure;
- labels explicitly distinguish “AgentOS semantic mapping”, “Fast-WAM policy action”, and “MuJoCo physical observation”.

The UI reuses the existing chat-first dispatch gate, automatic scroll, cancellation guards, read-only media routes, and responsive split layout. It does not reuse forklift skill labels or collision claims.

## Error Handling

- Missing LIBERO/MuJoCo dependency: fail preflight before loading 12 GB weights.
- Model or sidecar mismatch: fail before environment execution and record no successful evidence.
- CUDA out of memory: close the environment, release policy memory, retain the sanitized failure log, and stop the attempt.
- Non-finite/out-of-range action: stop the simulator before applying the action.
- EGL/render failure: fail the attempt; never publish an action-only run as a visual Demo.
- Policy timeout or episode timeout: terminal `FAILED` with the last observed state.
- Video, events, actions, or summary mismatch: manifest generation refuses the run.

## Testing and Acceptance

Local tests must cover:

- separate Fast-WAM rollout schema and strict validator;
- official success cannot be forged by summary fields;
- all actions contain exactly seven finite bounded values;
- five-attempt accounting and selected-attempt consistency;
- server routes expose only declared Fast-WAM media and evidence;
- the web tab loads the recorded run rather than the old single-call-only panel;
- structured phase projection uses observed frames and does not expose hidden reasoning;
- manifest hashes the new action, scene-variant, log, raw video, and presentation files;
- existing 164 Python tests and 40 JavaScript assertions remain green.

Remote acceptance additionally requires:

- real Fast-WAM checkpoint loading on CUDA;
- five deterministic custom-variant attempts completed or failed honestly;
- at least one attempt passes the official predicate before a success presentation is published;
- raw and presentation videos have matching frame counts and fps;
- visual review confirms a red apple, yellow plate, complete robot/workspace, visible grasp, transfer, and release, without mislabeled overlays.

## Delivery

Implement on a new branch based on `feature/demo-visual-physics-v2`, keep the completed forklift evidence unchanged, refresh the local console on port `8766`, push the public branch, and open or update a dedicated PR for the Fast-WAM manipulation feature.
