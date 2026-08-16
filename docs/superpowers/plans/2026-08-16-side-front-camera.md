# Side-Front Tracking Camera Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rear/establishing Isaac Sim camera with a smoothed side-front tracking camera that keeps the complete forklift and interacting payload visible.

**Architecture:** Keep the existing `CameraPose` and per-frame subject-fit pipeline. Change the desired pose to a forklift-relative front/side offset, constrain container phases to the open cutaway and back-wall limit, and extend the subject envelope to include an unattached payload only during close interaction phases. Re-render all formal evidence because the source camera changes every video frame.

**Tech Stack:** Python 3.14, `unittest`, Isaac Sim 6.0.1, USD/Replicator, ffmpeg, stdlib HTTP evidence console.

## Global Constraints

- The camera must stay in the forklift-local front half-plane with a visible lateral angle.
- The complete forklift and relevant payload must retain at least `0.05` normalized edge margin at 16:9.
- Container operation cameras must use the cutaway side and remain in front of the back wall.
- Camera height must stay at least `0.25 m` below the lowest warehouse ceiling beam.
- Do not change task motion, physics timelines, split-screen proportions, or right-side decision content.
- Formal evidence run IDs are `isaac-{scenario}-20260816-v5-r1` for `normal`, `recovery`, and `intervention`.

---

### Task 1: Camera Geometry Contract

**Files:**
- Modify: `tests/test_timeline.py:638-714`
- Modify: `demo/seer_demo/isaac/scene.py:132-348`

**Interfaces:**
- Consumes: `FrameState`, `CameraPose`, `local_from_world(...)`, `warehouse_layout_spec()`.
- Produces: `_payload_is_camera_subject(frame: FrameState) -> bool`, side-front poses from `camera_pose_for_frame(frame: FrameState) -> CameraPose`, and unchanged `camera_poses_for_timeline(timeline) -> tuple[CameraPose, ...]`.

- [x] **Step 1: Write failing side-front and payload-subject tests**

Add tests that convert each key pose into forklift-local coordinates and require `local_x > 0.5`, `abs(local_y) > 1.5`, and `abs(local_y) / local_x >= 0.25`. Add a close `precision_approach` frame assertion that `subject_world_corners(frame)` reaches at least `payload_x_m + 0.5` even while `payload_attached` is false.

```python
local_camera = local_from_world(
    (frame.base_x_m, frame.base_y_m, frame.base_z_m),
    frame.yaw_deg,
    pose.position,
)
self.assertGreater(local_camera[0], 0.5)
self.assertGreater(abs(local_camera[1]), 1.5)
self.assertGreaterEqual(abs(local_camera[1]) / local_camera[0], 0.25)
```

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=demo python3 -m unittest \
  tests.test_timeline.IsaacTimelineTests.test_camera_stays_side_front_relative_to_forklift \
  tests.test_timeline.IsaacTimelineTests.test_close_unattached_payload_is_in_camera_subject
```

Expected: FAIL because current camera local X is behind the forklift and unattached payload corners are excluded.

- [x] **Step 3: Implement the minimal side-front desired pose**

In `scene.py`, replace rearward phase directions with positive forward directions. Use the existing phase-specific lane Y values so container work remains on the negative-Y cutaway side and conveyor work remains in the central aisle. Reduce the hard minimum distance only as far as needed for a clear side angle; keep the margin-based expansion loop authoritative.

Add `_payload_is_camera_subject` with an explicit interaction-phase allow-list and a maximum horizontal payload distance. Use it from `subject_world_corners` so distant payloads do not shrink establishing shots.

- [x] **Step 4: Add and satisfy container back-wall and existing framing tests**

For container interaction phases, assert `pose.position[0] <= layout.container.position[0] + CONTAINER_LENGTH_M - 0.5`. Clamp the desired X before smoothing and keep the existing 5% frame margin loop.

Run:

```bash
PYTHONPATH=demo python3 -m unittest discover -s tests -p 'test_timeline.py'
```

Expected: all timeline tests PASS.

- [x] **Step 5: Update the formal strategy identifier and commit**

Change `demo/seer_demo/isaac/runner.py` from `subject_fit_smoothed_internal_views_v2` to `subject_fit_smoothed_side_front_v3`, update its exact expectations in `tests/test_manifest.py` and `tests/test_presentation.py`, then commit:

```bash
git add demo/seer_demo/isaac/scene.py demo/seer_demo/isaac/runner.py \
  tests/test_timeline.py tests/test_manifest.py tests/test_presentation.py
git commit -m "feat: track forklift from side-front camera"
```

### Task 2: Static and Full Regression

**Files:**
- Modify only if a regression reveals a camera-contract defect in Task 1 files.

**Interfaces:**
- Consumes: the Task 1 camera API and strategy identifier.
- Produces: a source tree cleared for formal Isaac rendering.

- [x] **Step 1: Run focused camera tests**

```bash
PYTHONPATH=demo python3 -m unittest discover -s tests -p 'test_timeline.py'
```

- [x] **Step 2: Run all local checks**

```bash
./scripts/run_demo.sh check
python3 -m compileall -q demo scripts tests
bash -n scripts/*.sh
git diff --check
```

Expected: 159 or more Python tests, 40 JavaScript protocol assertions, and all static checks PASS.

### Task 3: Formal V5 Isaac Evidence

**Files:**
- Replace: `demo/evidence/isaac-*-20260816-v4-r1/`
- Create: `demo/evidence/isaac-normal-20260816-v5-r1/`
- Create: `demo/evidence/isaac-recovery-20260816-v5-r1/`
- Create: `demo/evidence/isaac-intervention-20260816-v5-r1/`
- Modify: `demo/evidence/MANIFEST.json`

**Interfaces:**
- Consumes: Task 2 source snapshot, remote Isaac Sim root `/root/autodl-tmp/isaacsim601`, and warehouse assets `/root/autodl-tmp/simready_warehouse`.
- Produces: three self-contained evidence directories with `events.jsonl`, `summary.json`, `scene.usda`, `simulation.mp4`, and `presentation.mp4`.

- [x] **Step 1: Sync the exact committed source to the Isaac host**

Use remote source directory `/root/autodl-tmp/seer-hvla-v5-side-front` and evidence directory `/root/autodl-tmp/seer-v5-side-front-evidence`. Exclude `.git`, local credentials, and existing evidence videos.

- [x] **Step 2: Render all three scenarios**

On the Isaac host run:

```bash
export ISAAC_SIM_ROOT=/root/autodl-tmp/isaacsim601
export ISAAC_WAREHOUSE_ASSET_ROOT=/root/autodl-tmp/simready_warehouse
./scripts/run_isaac_demo.sh normal /root/autodl-tmp/seer-v5-side-front-evidence/isaac-normal-20260816-v5-r1 isaac-normal-20260816-v5-r1
./scripts/run_isaac_demo.sh recovery /root/autodl-tmp/seer-v5-side-front-evidence/isaac-recovery-20260816-v5-r1 isaac-recovery-20260816-v5-r1
./scripts/run_isaac_demo.sh intervention /root/autodl-tmp/seer-v5-side-front-evidence/isaac-intervention-20260816-v5-r1 isaac-intervention-20260816-v5-r1
```

- [x] **Step 3: Validate and download exact run artifacts**

Require all summaries to report `camera_strategy=subject_fit_smoothed_side_front_v3`, `collision_certified=true`, `forbidden_collision_count=0`, and `contact_violation_count=0`. Download only the five declared evidence files per run.

- [x] **Step 4: Build synchronized presentations**

For every V5 run execute:

```bash
for run_dir in \
  demo/evidence/isaac-normal-20260816-v5-r1 \
  demo/evidence/isaac-recovery-20260816-v5-r1 \
  demo/evidence/isaac-intervention-20260816-v5-r1; do
  .venv-presentation/bin/python scripts/build_split_presentation.py "$run_dir"
done
```

Require presentation frame count and fps to match each source video exactly.

- [x] **Step 5: Rebuild and verify the manifest**

```bash
python3 scripts/build_evidence_manifest.py demo/evidence demo/evidence/MANIFEST.json
python3 scripts/build_evidence_manifest.py demo/evidence /tmp/MANIFEST.v5.verify.json
diff <(jq 'del(.generated_at)' demo/evidence/MANIFEST.json) \
     <(jq 'del(.generated_at)' /tmp/MANIFEST.v5.verify.json)
```

### Task 4: Visual QA, Documentation, and Delivery

**Files:**
- Modify: `demo/README.md`
- Modify: `demo/CLAIMS.md`
- Modify: `demo/evidence/README.md`
- Modify: `demo/项目总结与交付说明.md`
- Modify: `进度记录.md`
- Modify: `待办事项.md`

**Interfaces:**
- Consumes: Task 3 V5 videos and manifest.
- Produces: user-visible local console, updated public branch, and PR evidence.

- [x] **Step 1: Create and inspect contact sheets**

Extract evenly spaced frames from all three raw videos and all three presentation videos. Reject any run where the forklift is cropped, the payload interaction is obscured, the camera crosses the container back wall, or a phase transition visibly jumps.

- [x] **Step 2: Update exact V5 documentation**

Replace V4 formal run IDs and the previous camera strategy with V5 values. State that the view is a smoothed side-front tracking camera and preserve the existing capability boundaries.

- [x] **Step 3: Run final verification**

```bash
./scripts/run_demo.sh check
python3 -m compileall -q demo scripts tests
bash -n scripts/*.sh
git diff --check
```

- [x] **Step 4: Commit and push**

```bash
git add -A
git commit -m "evidence: publish side-front Isaac V5 runs"
git push myfork feature/demo-visual-physics-v2
```

- [x] **Step 5: Refresh the persistent local console**

Set `commit_id=$(git rev-parse --short HEAD)` and copy the exact committed `demo` directory to `/Users/captainnemo/Library/Caches/com.seer.hvla.demo/$commit_id/demo`. Restart `com.seer.hvla.demo`, then verify `/`, `/api/runs`, and all three declared presentation media paths return HTTP 200.
