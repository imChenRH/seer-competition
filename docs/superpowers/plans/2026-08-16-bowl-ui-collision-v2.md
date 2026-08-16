# Bowl Demo, Unified Presentation, and Intervention Geometry V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the apple transfer with a higher-success canonical bowl-on-plate Fast-WAM run, make Fast-WAM presentation/web layout identical to the three forklift scenes, and eliminate obstacle interpenetration from the intervention evidence.

**Architecture:** Keep the Fast-WAM and Isaac execution backends independent, but adapt both into one common presentation schema and one web evidence workspace. Return Fast-WAM to canonical LIBERO task 8 assets and predicates. Define intervention obstacle geometry once in `isaac/layout.py`, then consume it from USD authoring and collision certification.

**Tech Stack:** Python 3.14/macOS tests, Python 3.12/Linux GPU rollout, LeRobot 0.6.2, Fast-WAM, LIBERO/MuJoCo 3.8.1, Isaac Sim 6.0.1, Pillow, ffmpeg/ffprobe, vanilla HTML/CSS/JavaScript, `unittest`.

## Global Constraints

- Branch is `feature/bowl-ui-collision-v2`, based on `14c918835d2507555f877874a95c5b1300ddfb48`.
- Fast-WAM emits every executed 7-D action; no rule controller may add or replace actions.
- Use canonical LIBERO `libero_goal` task id 8, original BDDL/assets, and unmodified `env.check_success()`.
- Run exactly five fixed official initial states and retain successful and failed attempt artifacts.
- Common presentation remains 2560×1080 with source video at 1280×720 and a frame-bound event clock.
- Intervention evidence must be rerendered; editing old video pixels is forbidden.
- Do not expose credentials, hidden reasoning, real-hardware claims, or production-safety claims.

---

### Task 1: Canonical Bowl-on-Plate Contract and Rollout

**Files:**
- Modify: `demo/seer_demo/fastwam/contracts.py`
- Modify: `demo/seer_demo/fastwam/scene_variant.py`
- Modify: `demo/seer_demo/fastwam/rollout.py`
- Modify: `scripts/run_fastwam_demo.sh`
- Modify: `tests/test_fastwam_contracts.py`
- Modify: `tests/test_fastwam_rollout.py`

**Interfaces:**
- Produces: `FASTWAM_SCENARIO = "fastwam_bowl_plate"`, `BowlPlateLiberoEnv`, physical state keys `bowl_*`, and a 300-step formal launcher.
- Consumes: canonical Fast-WAM checkpoint and existing action/event validators.

- [ ] **Step 1: Write failing canonical-scene tests**

Add tests that require the source to obtain task id 8, reject a task-name mismatch, avoid `_task_bddl_file` override, observe bodies `akita_black_bowl_1` and `plate_1`, emit `bowl_lift_m`, and use scenario `fastwam_bowl_plate`.

```python
def test_bowl_variant_uses_canonical_task_without_bddl_override(self):
    source = Path("demo/seer_demo/fastwam/scene_variant.py").read_text()
    self.assertIn('task.name != "put_the_bowl_on_the_plate"', source)
    self.assertNotIn("_task_bddl_file", source)
    self.assertIn('"akita_black_bowl_1"', source)
    self.assertIn('"plate_1"', source)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=demo python3 -m unittest tests.test_fastwam_contracts tests.test_fastwam_rollout -v
```

Expected: failures mention the old apple scenario/class/fields and BDDL override.

- [ ] **Step 3: Implement the canonical adapter**

Rename the wrapper and state fields, remove custom object registration and BDDL replacement, verify canonical bodies after reset, and change task/user labels. Keep two cameras, 224×224 observations, relative control, and fixed init states.

```python
FASTWAM_SCENARIO = "fastwam_bowl_plate"
CANONICAL_BOWL_BODY = "akita_black_bowl_1"
CANONICAL_PLATE_BODY = "plate_1"

class BowlPlateLiberoEnv:
    def reset(self, seed: int):
        observation, info = self._env.reset(seed=seed)
        bowl = self._body_position(CANONICAL_BOWL_BODY)
        self._body_position(CANONICAL_PLATE_BODY)
        self._initial_bowl_z = bowl[2]
        return observation, info
```

- [ ] **Step 4: Make the formal launcher use 300 steps**

Set `--max-steps 300`; record `step_budget` and the canonical prompt in summary. Do not change `n_action_steps` in this task.

- [ ] **Step 5: Verify GREEN and commit**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_fastwam_contracts tests.test_fastwam_rollout -v
bash -n scripts/run_fastwam_demo.sh
git add demo/seer_demo/fastwam scripts/run_fastwam_demo.sh tests/test_fastwam_contracts.py tests/test_fastwam_rollout.py
git commit -m "feat: restore canonical Fast-WAM bowl task"
```

### Task 2: Common Brain/Cerebellum Split Presentation

**Files:**
- Modify: `demo/seer_demo/presentation.py`
- Modify: `demo/seer_demo/fastwam/presentation.py`
- Modify: `scripts/build_fastwam_presentation.py`
- Modify: `tests/test_presentation.py`
- Modify: `tests/test_fastwam_presentation.py`

**Interfaces:**
- Produces: one `render_overlay(...)` layout for forklift and Fast-WAM; Fast-WAM source adapter returns the common snapshot mapping.
- Consumes: Task 1 `bowl_*` states, action records, and events.

- [ ] **Step 1: Write failing common-layout tests**

Require Fast-WAM snapshots to expose `goal`, `brain`, `cerebellum`, `safety`, and `audit`; require `render_fastwam_frames` to call the shared `render_overlay`; require bowl wording and reject apple wording.

```python
snapshot = fastwam_decision_snapshot(events, actions, summary, frame=42)
self.assertEqual(set(("goal", "brain", "cerebellum", "safety", "audit")) - snapshot.keys(), set())
self.assertEqual(snapshot["cerebellum"]["metrics"][0][0], "bowl_lift_m")
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_presentation tests.test_fastwam_presentation -v
```

Expected: missing common Fast-WAM snapshot and renderer reuse.

- [ ] **Step 3: Generalize common renderer contents, not geometry**

Add optional `source_title`, `scene_label`, `cerebellum.metrics`, and `safety.details` fields. Preserve all existing card coordinates and legacy forklift output. Map Fast-WAM observations/actions into those fields.

```python
"cerebellum": {
    "controller": "Fast-WAM 7-D relative action",
    "metrics": (
        ("bowl_lift_m", state.get("bowl_lift_m")),
        ("plate_xy_error_m", state.get("plate_xy_error_m")),
        ("gripper", "CLOSED" if state.get("gripper_closed") else "OPEN/TRANSITION"),
        ("policy", "MODEL CALL" if action.model_call else "ACTION QUEUE"),
    ),
},
```

- [ ] **Step 4: Delete the separate Fast-WAM card renderer**

Keep action/frame projection helpers, but render every Fast-WAM frame through `seer_demo.presentation.render_overlay`. Update presentation contract to `auditable_common_projection_v2`.

- [ ] **Step 5: Verify GREEN and commit**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_presentation tests.test_fastwam_presentation -v
git add demo/seer_demo/presentation.py demo/seer_demo/fastwam/presentation.py scripts/build_fastwam_presentation.py tests/test_presentation.py tests/test_fastwam_presentation.py
git commit -m "feat: unify Fast-WAM split presentation"
```

### Task 3: One Web Evidence Workspace for All Four Tabs

**Files:**
- Modify: `demo/web/index.html`
- Modify: `demo/web/app.js`
- Modify: `demo/web/styles.css`
- Modify: `demo/seer_demo/server.py`
- Modify: `tests/test_web_protocol.py`
- Modify: `tests/web_protocol_test.js`
- Modify: `tests/test_server.py`

**Interfaces:**
- Produces: the standard metrics/workspace/skill/lower-grid DOM for `fastwam_bowl_plate`; no separate active Fast-WAM page/player.
- Consumes: Task 1 scenario/summary and Task 2 presentation video.

- [ ] **Step 1: Write failing HTML/protocol tests**

Assert `fastwam-content` and `fastwam-video` are absent, only the standard `simulation-video` is used, the tab says `Fast-WAM 碗→盘`, and dispatching Fast-WAM unhides `evidence-content`.

```python
self.assertNotIn('id="fastwam-content"', html)
self.assertNotIn('id="fastwam-video"', html)
self.assertIn('data-scenario="fastwam"', html)
self.assertIn("把黑色碗放入盘子", script)
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_web_protocol tests.test_server -v
```

Expected: old separate Fast-WAM UI remains and server maps only the apple scenario.

- [ ] **Step 3: Reuse the standard DOM atomically**

Change `showFastWam` to populate standard metric, video, phase, skill, lower-left, and event-log nodes after one validated fetch batch. Retain generation guards after every await and before commit. Map `fastwam_bowl_plate` to the `fastwam` badge.

- [ ] **Step 4: Keep technical evidence inside the common lower grid**

Render official predicate, current 7-D action, bowl lift, target error, and five attempts in the standard lower-left panel. Remove obsolete separate-panel CSS.

- [ ] **Step 5: Verify GREEN and commit**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_web_protocol tests.test_server -v
git add demo/web demo/seer_demo/server.py tests/test_web_protocol.py tests/web_protocol_test.js tests/test_server.py
git commit -m "feat: unify Fast-WAM evidence workspace"
```

### Task 4: Non-Interpenetrating Intervention Obstacles

**Files:**
- Modify: `demo/seer_demo/isaac/layout.py`
- Modify: `demo/seer_demo/isaac/scene.py`
- Modify: `demo/seer_demo/isaac/collision.py`
- Modify: `demo/seer_demo/manifest.py`
- Modify: `tests/test_timeline.py`
- Modify: `tests/test_manifest.py`

**Interfaces:**
- Produces: `intervention_obstacle_geometry_specs()`, collision guard V4, and `obstacle_interpenetration_count`.
- Consumes: existing `BoxGeometrySpec`, warehouse layout, USD `box(...)`, OBB/SAT utilities, and formal summary validation.

- [ ] **Step 1: Write a failing overlap regression test**

The test must calculate each pair's XY intervals and Z intervals and require a positive separating axis or non-overlapping Z. It must also assert every bottom is nonnegative and scene/collision sources import the shared helper.

```python
def test_intervention_obstacles_are_floor_supported_and_pairwise_disjoint(self):
    specs = intervention_obstacle_geometry_specs()
    self.assertEqual(len(specs), 2)
    for spec in specs:
        self.assertGreaterEqual(spec.position[2] - spec.size[2] / 2, 0.0)
    self.assertGreater(obstacle_pair_gap(specs[0], specs[1]), 0.0)
```

- [ ] **Step 2: Verify RED against the current 3-D overlap**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_timeline.IsaacTimelineTests.test_intervention_obstacles_are_floor_supported_and_pairwise_disjoint -v
```

Expected: missing shared helper or negative pair gap.

- [ ] **Step 3: Implement shared obstacle specs**

Define two boxes with a 0.05 m horizontal gap, bottoms at `z=0`, unique names, and positions that still occlude the target. Author USD and collision OBBs exclusively from these specs.

```python
return (
    BoxGeometrySpec("FallenBoxA", "fault_obstacle", (0.85, 0.70, 0.85), (0.0, 0.0, 0.425)),
    BoxGeometrySpec("FallenBoxB", "fault_obstacle", (0.65, 0.65, 0.65), (-0.80, 0.10, 0.325)),
)
```

- [ ] **Step 4: Bind the static certificate into summaries**

Increment `COLLISION_GUARD_VERSION` to `2.5D_OBB_SAT_SWEEP_V4`; emit and require `obstacle_interpenetration_count == 0` in manifest validation.

- [ ] **Step 5: Verify GREEN and commit**

```bash
PYTHONPATH=demo python3 -m unittest tests.test_timeline tests.test_manifest -v
git add demo/seer_demo/isaac demo/seer_demo/manifest.py tests/test_timeline.py tests/test_manifest.py
git commit -m "fix: separate intervention obstacle geometry"
```

### Task 5: Formal GPU/Isaac Evidence, Documentation, and Delivery

**Files:**
- Replace: `demo/evidence/fastwam-apple-plate-20260816-v1-r4/`
- Create: `demo/evidence/fastwam-bowl-plate-20260816-v2-r1/`
- Replace: `demo/evidence/isaac-intervention-20260816-v5-r1/`
- Create: `demo/evidence/isaac-intervention-20260816-v6-r1/`
- Modify: `demo/evidence/MANIFEST.json`
- Modify: `demo/README.md`
- Modify: `demo/CLAIMS.md`
- Replace: `demo/FASTWAM-APPLE-PLATE-REPORT-2026-08-16.md`
- Create: `demo/FASTWAM-BOWL-PLATE-REPORT-2026-08-16.md`
- Modify: `demo/项目总结与交付说明.md`
- Modify: `进度记录.md`
- Modify: `待办事项.md`

**Interfaces:**
- Produces: formal bowl and corrected-intervention evidence packages, manifest hashes, public branch, draft PR, and exact-commit local deployment.
- Consumes: Tasks 1–4 exact committed source and the established secure AutoDL connection (connection values remain outside git and logs).

- [ ] **Step 1: Sync exact source to the GPU/Isaac host**

Create a git archive of the current commit, transfer it over the established SSH transport, verify the remote source commit marker, and keep credential values out of stdout/stderr.

- [ ] **Step 2: Run five canonical Fast-WAM attempts**

```bash
scripts/run_fastwam_demo.sh \
  /root/autodl-tmp/fastwam-env/bin/python \
  /root/autodl-tmp/fastwam_libero_uncond_2cam224 \
  /root/autodl-tmp/fastwam-bowl-plate-20260816-v2-r1 \
  fastwam-bowl-plate-20260816-v2-r1
```

Require five complete attempts and measured success strictly above 2/5. If the gate fails, retain the run as diagnostic evidence and return to Task 1 with one isolated hypothesis; do not publish it as improved.

- [ ] **Step 3: Rerender the intervention scenario**

Run the exact Task 4 commit in Isaac Sim 6.0.1 at 1280×720, 8 fps, then validate terminal `HUMAN_REQUIRED`, zero forbidden collisions, zero contact violations, and zero obstacle interpenetrations.

- [ ] **Step 4: Download and validate raw evidence**

Verify run ids, events, actions, state lengths, all five attempt media, USD scene, collision fields, ffprobe dimensions/fps/frame counts, and SHA-256 before moving packages under `demo/evidence`.

- [ ] **Step 5: Build common presentations and visually inspect contact sheets**

```bash
python3 scripts/build_fastwam_presentation.py demo/evidence/fastwam-bowl-plate-20260816-v2-r1
python3 scripts/build_split_presentation.py demo/evidence/isaac-intervention-20260816-v6-r1
```

Confirm the bowl is visible, Fast-WAM right panel matches forklift cards, and the two intervention obstacles have visible separation in source and split videos.

- [ ] **Step 6: Replace superseded formal evidence and rebuild manifest twice**

Remove the old apple and V5 intervention directories only after the new packages pass. Rebuild to two temporary manifests and compare them after removing `generated_at`, then install the verified manifest.

- [ ] **Step 7: Update claims and reports**

State the exact measured bowl result and budget. Preserve the historical 2/5 apple result only as superseded history; do not call the new five-seed result a general success rate.

- [ ] **Step 8: Run final verification**

```bash
./scripts/run_demo.sh check
git diff --check
python3 scripts/build_evidence_manifest.py demo/evidence /tmp/bowl-manifest.json
```

Also issue local HTTP 200 checks for page/summary/events/actions/media and an HTTP 206 100-byte Range request for both presentations.

- [ ] **Step 9: Commit, push, open a draft PR, and deploy**

```bash
git add demo docs/superpowers 进度记录.md 待办事项.md tests scripts
git commit -m "evidence: publish unified bowl and intervention demos"
git push -u myfork feature/bowl-ui-collision-v2
```

Create a draft PR against `imChenRH/master`. Deploy an exact `git archive HEAD demo` cache through `launchctl` on `127.0.0.1:8766`, then verify the running process path contains the final commit hash.
