# Fast-WAM Red Apple to Yellow Plate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish an evidence-backed Fast-WAM rollout in which the policy's real 7-D actions move a custom red-apple object onto a yellow plate in LIBERO/MuJoCo.

**Architecture:** Keep the validated forklift track unchanged and add a separate `seer_demo.fastwam` package for scene registration, rollout recording, action/event validation, and presentation rendering. The existing server and manifest dispatch validation by evidence source; the Fast-WAM web tab loads a recorded manipulation run rather than presenting the old single-call-only metrics.

**Tech Stack:** Python 3.12/3.14, `unittest`, LeRobot 0.6.2, Fast-WAM LIBERO 2-camera checkpoint, `hf-libero` 0.1.4, MuJoCo 3.8.1/EGL, PyTorch/CUDA, Pillow, ffmpeg, vanilla HTML/CSS/JavaScript.

## Global Constraints

- Use branch `feature/fastwam-apple-plate`, based on commit `9b717c8` from `feature/demo-visual-physics-v2`.
- Keep all existing forklift source and V5 evidence behavior unchanged.
- Formal scenario is `fastwam_apple_plate`; formal source is `fastwam_policy`.
- Official base task is `libero_goal` task id `8`, `put_the_bowl_on_the_plate`.
- AgentOS user task is `把红色苹果放入黄色盘子`; the policy prompt is exactly `Put the bowl on the plate`.
- Model execution uses the existing local checkpoint `/root/autodl-tmp/models/fastwam_libero_uncond_2cam224` and produces exactly seven finite bounded values per action.
- Execute five fixed initialization states; publish a successful presentation only if at least one attempt reports the official LIBERO success predicate.
- Do not substitute a rule controller after Fast-WAM begins execution.
- Do not expose hidden reasoning; show only configured dispatch, measured actions, simulator observations, timings, and terminal predicates.
- Formal run id is `fastwam-apple-plate-20260816-v1-r1`.
- Raw and presentation videos must have matching fps and frame counts; presentation resolution is 2560x1080.

---

### Task 1: Independent Fast-WAM Evidence Contract

**Files:**
- Create: `demo/seer_demo/fastwam/__init__.py`
- Create: `demo/seer_demo/fastwam/contracts.py`
- Create: `tests/test_fastwam_contracts.py`
- Modify: `demo/seer_demo/contracts.py:13-15`

**Interfaces:**
- Consumes: `seer_demo.contracts.Event`, `ValidationSummary`, `load_events(...)`, and `validate_events(...)`.
- Produces: `ActionRecord.from_dict(value)`, `load_action_records(path)`, `validate_action_records(records, run_id, frame_count)`, `validate_fastwam_events(events)`, and `validate_fastwam_package(summary, events, actions)`.

- [ ] **Step 1: Write failing event-source and action-record tests**

Create tests that require `EventWriter(..., source="fastwam_policy")` to be accepted and malformed action records to fail closed:

```python
def test_fastwam_actions_require_contiguous_finite_7d_values(self):
    valid = [
        ActionRecord("1.0", "wam-1", 0, 0, 0.0, (0.0,) * 7, True, 0.21),
        ActionRecord("1.0", "wam-1", 1, 1, 0.05, (0.1,) * 7, False, 0.001),
    ]
    result = validate_action_records(valid, "wam-1", frame_count=2)
    self.assertEqual(result.action_count, 2)
    self.assertEqual(result.policy_call_count, 1)
    for broken in (
        [replace(valid[0], sequence=2)],
        [replace(valid[0], action=(0.0,) * 6)],
        [replace(valid[0], action=(float("nan"),) + (0.0,) * 6)],
        [replace(valid[0], observed_frame=2)],
    ):
        with self.assertRaises(ValueError):
            validate_action_records(broken, "wam-1", frame_count=2)
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=demo python3 -m unittest tests.test_fastwam_contracts
```

Expected: import failure because `seer_demo.fastwam.contracts` does not exist and the shared writer rejects `fastwam_policy`.

- [ ] **Step 3: Implement strict action and successful-event validators**

Add `fastwam_policy` to `ALLOWED_SOURCES`. Define:

```python
FASTWAM_SCENARIO = "fastwam_apple_plate"
FASTWAM_SKILLS = (
    "ARM-PER-01", "ARM-PLAN-01", "WAM-ACT-01", "ARM-OP-01",
    "ARM-OP-02", "ARM-OP-03", "ARM-OP-04", "ARM-VER-01",
)

@dataclass(frozen=True, slots=True)
class ActionRecord:
    schema_version: str
    run_id: str
    sequence: int
    observed_frame: int
    sim_time_s: float
    action: tuple[float, ...]
    model_call: bool
    latency_s: float
```

`validate_fastwam_events` must require a `task_started`, a started/completed pair for every `FASTWAM_SKILLS` item, and a final `task_completed`. `ARM-VER-01` completion and the terminal event must both contain `state.official_success=true`. A failed run may terminate with `task_failed`, but it may not contain a completed verification event.

- [ ] **Step 4: Add package-level attempt and summary binding tests**

Require exactly five attempts with indices `0..4`; successful summary selection must reference the first successful attempt; `selected_attempt=null` is allowed only when all attempts failed. Require `action_count`, `policy_call_count`, `frame_count`, run id, source, and scenario to match validated inputs.

```python
summary["attempts"] = [
    {"attempt_index": i, "seed": 202608160 + i, "init_state_id": i,
     "success": i == 2, "executed_steps": 80 + i,
     "policy_calls": 8 + i, "terminal_reason": "success" if i == 2 else "timeout"}
    for i in range(5)
]
summary["selected_attempt"] = 2
self.assertEqual(
    validate_fastwam_package(summary, events, actions).terminal_status,
    "COMPLETED",
)
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
PYTHONPATH=demo python3 -m unittest tests.test_fastwam_contracts tests.test_contracts
```

Expected: all focused tests PASS.

Commit:

```bash
git add demo/seer_demo/contracts.py demo/seer_demo/fastwam tests/test_fastwam_contracts.py
git commit -m "feat: validate Fast-WAM rollout evidence"
```

### Task 2: LIBERO Apple/Plate Scene and Rollout Harness

**Files:**
- Create: `demo/seer_demo/fastwam/assets/red_apple.xml`
- Create: `demo/seer_demo/fastwam/assets/put_red_apple_on_yellow_plate.bddl`
- Create: `demo/seer_demo/fastwam/scene_variant.py`
- Create: `demo/seer_demo/fastwam/rollout.py`
- Create: `scripts/run_fastwam_demo.sh`
- Create: `tests/test_fastwam_rollout.py`

**Interfaces:**
- Consumes: official `libero_goal` suite task id `8`, `LiberoEnv`, `FastWAMPolicy`, LeRobot processor pipelines, and Task 1 contracts.
- Produces: `register_scene_objects()`, `ApplePlateLiberoEnv`, `derive_phase(observation)`, `validate_policy_action(action)`, CLI `python -m seer_demo.fastwam.rollout`, and formal raw evidence files.

- [ ] **Step 1: Write failing static scene-contract tests**

Parse XML/BDDL without importing LIBERO. Require:

```python
def test_variant_contains_physical_red_apple_and_yellow_plate_goal(self):
    apple = ET.parse(ASSETS / "red_apple.xml")
    self.assertTrue(apple.findall(".//geom[@type='sphere']"))
    self.assertIn("0.80 0.03 0.02 1", xml_text)
    bddl = (ASSETS / "put_red_apple_on_yellow_plate.bddl").read_text()
    self.assertIn("red_apple_1 - red_apple", bddl)
    self.assertIn("yellow_plate_1 - yellow_plate", bddl)
    self.assertIn("(On red_apple_1 yellow_plate_1)", bddl)
```

Also require the BDDL to retain all original fixtures, distractors, initial regions, and object ordering so the official init-state vector remains compatible.

- [ ] **Step 2: Run static tests and verify RED**

Run:

```bash
PYTHONPATH=demo python3 -m unittest tests.test_fastwam_rollout
```

Expected: missing asset and module failures.

- [ ] **Step 3: Implement registered objects and environment override**

`RedApple` loads `red_apple.xml` as a free-joint `MujocoXMLObject`. The XML contains a collision sphere, matching visual sphere, and non-colliding stem plus `bottom_site`, `top_site`, and `horizontal_radius_site`. `YellowPlate` subclasses LIBERO's `Plate`, removes material bindings from its geoms, and sets `rgba="0.95 0.70 0.04 1"`.

`ApplePlateLiberoEnv` subclasses `LiberoEnv`, calls the official suite/task constructor, then replaces only `_task_bddl_file` with the packaged overlay and keeps `task_description="Put the bowl on the plate"`.

- [ ] **Step 4: Write action safety and observed-phase tests**

Use plain dictionaries so tests do not need CUDA:

```python
self.assertEqual(validate_policy_action(np.zeros(7)).shape, (7,))
for value in (np.zeros(6), np.array([0, 0, 0, 0, 0, 0, np.nan]), np.full(7, 1.1)):
    with self.assertRaises(ValueError):
        validate_policy_action(value)

self.assertEqual(derive_phase(initial_obs), "ARM-OP-01")
self.assertEqual(derive_phase({**initial_obs, "apple_lift_m": 0.05}), "ARM-OP-02")
self.assertEqual(derive_phase({**initial_obs, "apple_lift_m": 0.05, "plate_xy_error_m": 0.10}), "ARM-OP-03")
self.assertEqual(derive_phase({**initial_obs, "official_success": True}), "ARM-VER-01")
```

- [ ] **Step 5: Implement late-import rollout and deterministic attempt accounting**

The module must import Torch, LeRobot, LIBERO, and MuJoCo only inside `run_remote_rollout`. For each init state `0..4`:

1. reset the policy and `ApplePlateLiberoEnv`;
2. preprocess the two RGB observations and proprioception with official LeRobot environment and policy processors;
3. call `policy.select_action` under `torch.inference_mode()`;
4. post-process and validate the `[7]` action before `env.step`;
5. write `actions.jsonl`, sampled simulator state, model-call latency, and full-resolution agent-view frames;
6. stop only on official success, environment termination, policy error, or 300 steps;
7. retain all five result rows and select the first success.

The CLI is:

```bash
python -m seer_demo.fastwam.rollout \
  --model-dir /root/autodl-tmp/models/fastwam_libero_uncond_2cam224 \
  --output-dir /root/autodl-tmp/seer-fastwam-evidence/fastwam-apple-plate-20260816-v1-r1 \
  --run-id fastwam-apple-plate-20260816-v1-r1 \
  --attempts 5 --fps 20 --width 1280 --height 720
```

- [ ] **Step 6: Implement shell preflight and run focused tests**

`scripts/run_fastwam_demo.sh` must require Linux, an executable Python, model config/safetensors, the officially resolved `Mujoco==3.8.1`, CUDA availability, EGL, at least 10 GB free disk before rendering, and a new output directory. The checkpoint already exists outside the output directory, so this threshold covers dependencies and five recorded attempts without pretending that a second 12 GB checkpoint copy is required. It invokes the module without `eval` or shell-generated Python.

Run:

```bash
PYTHONPATH=demo python3 -m unittest tests.test_fastwam_rollout tests.test_fastwam_contracts
bash -n scripts/run_fastwam_demo.sh
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add demo/seer_demo/fastwam scripts/run_fastwam_demo.sh tests/test_fastwam_rollout.py
git commit -m "feat: add Fast-WAM apple plate rollout"
```

### Task 3: Server and Manifest Dispatch by Evidence Source

**Files:**
- Modify: `demo/seer_demo/server.py`
- Modify: `demo/seer_demo/manifest.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_manifest.py`

**Interfaces:**
- Consumes: Task 1 `validate_fastwam_package(...)` and Fast-WAM summary declarations.
- Produces: Fast-WAM-aware `EvidenceCatalog.get_summary`, `/api/runs/<run_id>/actions`, enriched `/api/fastwam`, and manifest hashes for every additional evidence file.

- [ ] **Step 1: Write failing source-dispatch server tests**

Create a temporary valid Fast-WAM package and assert:

```python
status, _, body = self.fetch("/api/fastwam")
payload = json.loads(body)
self.assertEqual(status, 200)
self.assertEqual(payload["rollout"]["run_id"], "fastwam-test")
self.assertTrue(payload["rollout"]["official_success"])

status, headers, body = self.fetch("/api/runs/fastwam-test/actions")
self.assertEqual(status, 200)
self.assertEqual(headers["Content-Type"], "application/x-ndjson; charset=utf-8")
```

Forge `official_success=true` in only the summary and require the run to disappear from catalog results.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONPATH=demo python3 -m unittest tests.test_server
```

Expected: Fast-WAM runs are rejected by forklift scenario validation and `/actions` returns 404.

- [ ] **Step 3: Implement validator dispatch and declared action route**

Read the summary first, load events and the declared `actions_file`, then call `validate_fastwam_package` only when `source == "fastwam_policy"`; retain `validate_scenario_events` for all existing sources. `media_path` and `actions_path` must reuse `_run_dir` and basename allow-list checks.

Enrich `/api/fastwam` with the latest valid rollout summary while retaining the old single-call proof under `technical_validation`.

- [ ] **Step 4: Write failing manifest tests for additional files**

Require manifest records to hash:

```python
summary["additional_evidence_files"] = [
    "actions.jsonl", "scene_variant.json", "run.log", "evaluation.json"
]
self.assertEqual(
    record["files"]["actions.jsonl"]["sha256"],
    sha256_file(run / "actions.jsonl"),
)
```

Reject absolute paths, traversal, missing files, duplicates, and a Fast-WAM summary whose selected attempt disagrees with `evaluation.json`.

- [ ] **Step 5: Implement manifest source dispatch and hashes**

`build_manifest` must validate Fast-WAM packages without applying Isaac collision fields, probe both videos, and add `policy_checkpoint`, `official_success`, `attempt_count`, and `selected_attempt` to the run record. Existing Isaac manifest records must remain byte-for-byte equivalent except for `generated_at`.

- [ ] **Step 6: Run tests and commit**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_server tests.test_manifest tests.test_fastwam_contracts
git add demo/seer_demo/server.py demo/seer_demo/manifest.py tests/test_server.py tests/test_manifest.py
git commit -m "feat: serve validated Fast-WAM rollout evidence"
```

### Task 4: Synchronized Fast-WAM Split Presentation

**Files:**
- Create: `demo/seer_demo/fastwam/presentation.py`
- Create: `scripts/build_fastwam_presentation.py`
- Create: `tests/test_fastwam_presentation.py`

**Interfaces:**
- Consumes: validated events/actions/summary plus `simulation.mp4`.
- Produces: `action_at_frame(actions, frame)`, `fastwam_snapshot(events, actions, frame)`, `render_fastwam_panel(...)`, and a clock-bound `presentation.mp4`.

- [ ] **Step 1: Write failing snapshot and no-hidden-reasoning tests**

Require the projection to choose the latest observed event and action without mutating inputs:

```python
snapshot = fastwam_snapshot(events, actions, frame=42)
self.assertEqual(snapshot.phase, "ARM-OP-02")
self.assertEqual(snapshot.action, actions[42].action)
self.assertEqual(snapshot.layer, "Fast-WAM policy action")
self.assertNotIn("reasoning", snapshot.to_dict())
self.assertNotIn("thought", snapshot.to_dict())
```

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_fastwam_presentation
```

Expected: module import failure.

- [ ] **Step 3: Implement panel renderer and ffmpeg clock contract**

Render 1280x1080 right panels with:

- task and semantic mapping;
- active structured phase;
- seven labeled action values `dx/dy/dz/drx/dry/drz/grip`;
- model-call marker and measured latency;
- apple lift, plate XY error, gripper state, and official success;
- selected attempt and five-attempt outcome strip;
- immutable claim-boundary footer.

Use blue/amber/green/red phase themes. Green is allowed only after `official_success=true`.

- [ ] **Step 4: Bind source and presentation media exactly**

The builder must ffprobe the source, render exactly one panel frame per source frame, combine the source and panel with ffmpeg to 2560x1080, then require identical fps/frame count/duration before updating summary presentation fields.

- [ ] **Step 5: Run tests and commit**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_fastwam_presentation tests.test_presentation
python3 -m compileall -q demo/seer_demo/fastwam scripts/build_fastwam_presentation.py
git add demo/seer_demo/fastwam/presentation.py scripts/build_fastwam_presentation.py tests/test_fastwam_presentation.py
git commit -m "feat: render Fast-WAM split presentation"
```

### Task 5: Full Fast-WAM Web Evidence View

**Files:**
- Modify: `demo/web/index.html`
- Modify: `demo/web/styles.css`
- Modify: `demo/web/app.js`
- Modify: `demo/web/protocol.js`
- Modify: `tests/test_web_protocol.py`
- Modify: `tests/web_protocol_test.js`

**Interfaces:**
- Consumes: `/api/fastwam`, `/api/runs/<id>/events`, `/api/runs/<id>/actions`, and declared presentation media.
- Produces: a chat-gated manipulation evidence view synchronized to the Fast-WAM presentation video.

- [ ] **Step 1: Write failing HTML and protocol tests**

Replace the old “future connection path” expectation with real evidence requirements:

```python
self.assertIn('id="fastwam-video"', html)
self.assertIn('id="fastwam-action-values"', html)
self.assertIn('id="fastwam-attempts"', html)
self.assertIn('id="fastwam-official-success"', html)
self.assertNotIn("机械臂模型、任务数据与后训练", html)
self.assertIn("fetchFastWamEvidence", source)
self.assertIn("syncFastWamPlayback", source)
```

JavaScript assertions must reject a rollout with a non-seven-dimensional action, mismatched run id, sequence gap, or action frame outside the video range.

- [ ] **Step 2: Run web tests and verify RED**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_web_protocol
```

Expected: missing elements and reducer functions.

- [ ] **Step 3: Implement atomic Fast-WAM fetch and playback reducer**

`fetchFastWamEvidence` fetches summary, events, and actions under one render generation, validates all three before changing the DOM, and then sets the declared presentation URL. Every awaited boundary checks scenario/generation ownership.

`syncFastWamPlayback(currentTime, fps)` uses `floor(currentTime * fps)` to project the latest action and event. It updates seven values, phase color, latency, observed physical state, and official-success label. It never displays a completed state before the corresponding observed frame.

- [ ] **Step 4: Implement the full-width evidence layout**

Retain the existing chat-first dispatch and automatic scroll. Show:

- presentation video at 16:9;
- compact technical-validation metrics;
- structured task mapping and selected attempt;
- current seven-value action strip and measured model-call latency;
- five-attempt results and strict claim boundary.

The old pending card is removed. Failure runs use a red terminal theme and remain viewable.

- [ ] **Step 5: Run protocol tests and commit**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_web_protocol tests.test_server
/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/web_protocol_test.js
git add demo/web tests/test_web_protocol.py tests/web_protocol_test.js
git commit -m "feat: show Fast-WAM manipulation evidence"
```

### Task 6: Remote Environment and Real Five-Attempt Evaluation

**Files:**
- Create remotely: `/root/autodl-tmp/seer-fastwam-apple-plate/`
- Create remotely: `/root/autodl-tmp/seer-fastwam-evidence/fastwam-apple-plate-20260816-v1-r1/`
- Create locally after download: `demo/evidence/fastwam-apple-plate-20260816-v1-r1/`

**Interfaces:**
- Consumes: exact committed Task 1-5 source, remote Fast-WAM conda environment, local checkpoint, CUDA, and EGL.
- Produces: five-attempt evaluation records and one selected formal rollout if any attempt succeeds.

- [ ] **Step 1: Establish disk-safe remote dependencies**

Record disk usage, then install only the missing environment packages into `/root/autodl-tmp/conda/envs/fastwam`:

```bash
/root/autodl-tmp/conda/envs/fastwam/bin/python -m pip install \
  -e '/root/autodl-tmp/lerobot[libero]'
```

Require at least 10 GB free after installation and remove only pip's download cache after successful installation. Do not delete the checkpoint, Isaac evidence, or user files.

- [ ] **Step 2: Run canonical task-id-8 preflight**

Before the custom variant, create one official `libero_goal` task-id-8 environment, reset it, render both required cameras, load the local policy, produce one finite `[7]` action, and close the environment. Save a sanitized preflight JSON containing versions, task id/name, shapes, and elapsed time.

- [ ] **Step 3: Sync exact committed source and execute five attempts**

Use a tar archive from `git archive HEAD`, not the dirty worktree. Exclude all credentials and existing evidence. Run:

```bash
export MUJOCO_GL=egl
export PYTHONPATH=/root/autodl-tmp/seer-fastwam-apple-plate/demo
/root/autodl-tmp/seer-fastwam-apple-plate/scripts/run_fastwam_demo.sh \
  /root/autodl-tmp/conda/envs/fastwam/bin/python \
  /root/autodl-tmp/models/fastwam_libero_uncond_2cam224 \
  /root/autodl-tmp/seer-fastwam-evidence/fastwam-apple-plate-20260816-v1-r1 \
  fastwam-apple-plate-20260816-v1-r1
```

- [ ] **Step 4: Enforce publication rule and download evidence**

Require five result rows and verify the selected attempt is the first `success=true`. If no attempt succeeds, stop delivery, preserve the failure summary, and diagnose the real rollout; do not build a green presentation.

Download only declared formal files. Re-run Task 1 validators and ffprobe locally before adding them to Git.

### Task 7: Presentation, Manifest, Documentation, and Delivery

**Files:**
- Create: `demo/evidence/fastwam-apple-plate-20260816-v1-r1/`
- Modify: `demo/evidence/MANIFEST.json`
- Modify: `demo/evidence/README.md`
- Modify: `demo/README.md`
- Modify: `demo/CLAIMS.md`
- Modify: `demo/AUDIT.md`
- Modify: `demo/项目总结与交付说明.md`
- Modify: `进度记录.md`
- Modify: `待办事项.md`

**Interfaces:**
- Consumes: validated Task 6 raw evidence and Task 4 presentation builder.
- Produces: public branch, dedicated PR, and persistent local console on port 8766.

- [ ] **Step 1: Build and validate the split presentation**

```bash
.venv-presentation/bin/python scripts/build_fastwam_presentation.py \
  demo/evidence/fastwam-apple-plate-20260816-v1-r1
```

Require 2560x1080, source-matching fps/frame count/duration, seven visible action values, attempt statistics, and green terminal styling only after the official success frame.

- [ ] **Step 2: Perform visual QA**

Create a 12-frame contact sheet plus close-up sheets around approach, grasp, lift, transfer, release, and terminal verification. Reject the evidence if the object does not read as a red apple, the target does not read as a yellow plate, the complete robot/workspace is obscured, the grasp is not visible, or overlays disagree with the physical frame.

- [ ] **Step 3: Rebuild the manifest twice**

```bash
python3 scripts/build_evidence_manifest.py demo/evidence demo/evidence/MANIFEST.json
python3 scripts/build_evidence_manifest.py demo/evidence /tmp/MANIFEST.fastwam.verify.json
diff <(jq 'del(.generated_at)' demo/evidence/MANIFEST.json) \
     <(jq 'del(.generated_at)' /tmp/MANIFEST.fastwam.verify.json)
```

- [ ] **Step 4: Update claims without erasing the legacy proof**

Document both facts separately:

- legacy single-call evidence proves model load plus one `[1,7]` output;
- the new formal run proves one recorded custom LIBERO visual variant and reports all five fixed-attempt outcomes;
- neither proves apple-specific training, real-robot transfer, paper-wide success rates, or production safety.

- [ ] **Step 5: Run final verification**

```bash
./scripts/run_demo.sh check
python3 -m compileall -q demo scripts tests
bash -n scripts/*.sh
git diff --check
```

Require all Python tests and JavaScript assertions to pass. Run a sensitive-value scan and confirm no credentials, tokens, private keys, or remote passwords are tracked.

- [ ] **Step 6: Commit, push, and open a dedicated draft PR**

```bash
git add -A
git commit -m "evidence: publish Fast-WAM apple plate rollout"
git push -u myfork feature/fastwam-apple-plate
```

Open a draft PR from `captainNemoCheng:feature/fastwam-apple-plate` to `imChenRH:master`, stating measured five-attempt results and the custom-variant boundary.

- [ ] **Step 7: Refresh and verify local port 8766**

Resolve `commit_id=$(git rev-parse --short HEAD)` and copy the exact committed `demo` tree into `/Users/captainnemo/Library/Caches/com.seer.hvla.demo/$commit_id/demo`; restart `com.seer.hvla.demo` with explicit `launchctl submit -p /usr/bin/env`; require HTTP 200 for `/`, `/api/fastwam`, the new run summary/events/actions, and the presentation media path.
