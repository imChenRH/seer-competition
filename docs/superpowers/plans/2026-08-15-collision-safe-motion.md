# Collision-Safe Warehouse Motion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate visible vehicle, fork, payload, and conveyor interpenetration while preserving the deterministic evidence contract.

**Architecture:** Add a pure-Python 2.5D collision kernel that certifies every pose and swept transition before Isaac authors a transform. Split the conveyor approach into clearance-safe phases, derive all support heights from shared geometry constants, and record collision certification in the formal summary.

**Tech Stack:** Python 3.11+, dataclasses, unittest, OpenUSD/Isaac Sim 6.0.1, ffmpeg/ffprobe.

## Global Constraints

- Do not add third-party Python dependencies.
- XY collision uses OBB SAT; Z uses interval overlap.
- Swept translation step is at most 0.025 m; swept yaw step is at most 0.5°.
- Forbidden body/static clearance is 0.05 m.
- Payload support clearance is 0.005 m with at most 0.01 m error.
- A failed guard must stop evidence generation before terminal success or Manifest creation.
- Keep existing event type ordering and nine-skill business semantics.

---

### Task 1: Pure-Python collision kernel

**Files:**
- Create: `demo/seer_demo/isaac/collision.py`
- Modify: `tests/test_timeline.py`

**Interfaces:**
- Produces: `OrientedBox`, `Pose2D`, `boxes_overlap_3d()`, `swept_poses()`, `find_forbidden_collisions()`.
- Consumes: only `math` and dataclasses.

- [ ] **Step 1: Write failing tests for the known conveyor clip and safe separated boxes**

```python
def test_swept_guard_detects_the_old_diagonal_conveyor_clip(self):
    start = Pose2D(-0.985402, 1.191240, 8.0)
    end = Pose2D(-9.281922, -3.855056, -6.0)
    conveyor = OrientedBox("conveyor_keepout", (-6.0, -4.2), (3.2, 1.35), -6.0, 0.0, 0.78)
    report = find_forbidden_collisions(start, end, (conveyor,))
    self.assertEqual(report[0].static_name, "conveyor_keepout")

def test_obb_guard_respects_xy_and_z_separation(self):
    low_box = OrientedBox("low", (0.0, 0.0), (1.0, 1.0), 0.0, 0.0, 0.5)
    high_box = OrientedBox("high", (0.0, 0.0), (1.0, 1.0), 0.0, 0.6, 1.0)
    left_box = OrientedBox("left", (-2.0, 0.0), (1.0, 1.0), 25.0, 0.0, 1.0)
    right_box = OrientedBox("right", (2.0, 0.0), (1.0, 1.0), -25.0, 0.0, 1.0)
    self.assertFalse(boxes_overlap_3d(low_box, high_box))
    self.assertFalse(boxes_overlap_3d(left_box, right_box))
```

- [ ] **Step 2: Run the focused tests and confirm import/API failure**

Run: `PYTHONPATH=demo python3 -m unittest tests.test_timeline.IsaacTimelineTests.test_swept_guard_detects_the_old_diagonal_conveyor_clip -v`

Expected: fail because `seer_demo.isaac.collision` does not exist.

- [ ] **Step 3: Implement SAT, Z intervals, shortest-yaw interpolation, and deterministic collision reports**

```python
@dataclass(frozen=True, slots=True)
class OrientedBox:
    name: str
    center: tuple[float, float]
    size: tuple[float, float]
    yaw_deg: float
    z_min: float
    z_max: float

def swept_poses(start: Pose2D, end: Pose2D, *, translation_step_m=0.025, yaw_step_deg=0.5):
    dx, dy = end.x_m - start.x_m, end.y_m - start.y_m
    dyaw = (end.yaw_deg - start.yaw_deg + 180.0) % 360.0 - 180.0
    count = max(1, math.ceil(math.hypot(dx, dy) / translation_step_m), math.ceil(abs(dyaw) / yaw_step_deg))
    return tuple(Pose2D(start.x_m + dx * i / count, start.y_m + dy * i / count, start.yaw_deg + dyaw * i / count) for i in range(count + 1))

def boxes_overlap_3d(left: OrientedBox, right: OrientedBox, *, margin_xy=0.0):
    if left.z_max <= right.z_min or right.z_max <= left.z_min:
        return False
    for axis in left.axes + right.axes:
        if left.project(axis, margin_xy).is_disjoint(right.project(axis, 0.0)):
            return False
    return True
```

- [ ] **Step 4: Run focused tests and the complete timeline test module**

Run: `PYTHONPATH=demo python3 -m unittest tests.test_timeline -v`

Expected: all tests pass.

### Task 2: Shared support geometry and physically valid payload heights

**Files:**
- Modify: `demo/seer_demo/isaac/layout.py`
- Modify: `demo/seer_demo/isaac/scene.py`
- Modify: `demo/seer_demo/isaac/timeline.py`
- Modify: `tests/test_timeline.py`

**Interfaces:**
- Produces: `container_payload_target`, `conveyor_payload_target`, `payload_attachment_z_offset_m`, and `conveyor_geometry_specs()` derived from one geometry contract.
- Consumes: `pallet_part_specs()` dimensions and fork geometry.

- [ ] **Step 1: Write failing tests for the 0.23 m penetration, payload continuity, and open fork channels**

```python
def test_payload_bottom_rests_five_mm_above_conveyor_support(self):
    self.assertAlmostEqual(layout.conveyor_payload_target[2], 0.785, places=6)

def test_attachment_does_not_teleport_payload_vertically(self):
    self.assertLessEqual(abs(after.payload_z_m - before.payload_z_m), 0.02)

def test_conveyor_support_lanes_leave_both_fork_channels_open(self):
    for lane_min, lane_max in lanes:
        for pocket_min, pocket_max in ((-0.385, -0.255), (0.255, 0.385)):
            self.assertTrue(lane_max <= pocket_min or pocket_max <= lane_min)
```

- [ ] **Step 2: Run the three tests and verify failures show the old 0.55 m target/solid base behavior**

Run: `PYTHONPATH=demo python3 -m unittest tests.test_timeline -v`

- [ ] **Step 3: Derive floor, fork, pallet, and roller heights and replace the solid conveyor base**

Use literals fixed by the spec: floor top `0.12`, insertion pallet root `0.125`, roller top `0.78`, released pallet root `0.785`, attached root offset `0.015`.

- [ ] **Step 4: Move the green target to `/World/Visuals/ConveyorTarget` with collision disabled**

- [ ] **Step 5: Run timeline and scene-contract tests**

Run: `PYTHONPATH=demo python3 -m unittest tests.test_timeline -v`

Expected: all tests pass with no vertical jump or support penetration.

### Task 3: Collision-safe phase path

**Files:**
- Modify: `demo/seer_demo/isaac/collision.py`
- Modify: `demo/seer_demo/isaac/timeline.py`
- Modify: `tests/test_timeline.py`

**Interfaces:**
- Produces: `certify_timeline(timeline) -> CollisionCertification` and collision-safe `prealign_conveyor` phase.
- Consumes: `warehouse_layout_spec()` and Task 1 collision primitives.

- [ ] **Step 1: Write failing whole-timeline tests for all three scenarios**

```python
def test_all_scenarios_have_zero_forbidden_swept_collisions(self):
    for scenario in ("normal", "recovery", "intervention"):
        result = certify_timeline(build_timeline(scenario, fps=8))
        self.assertEqual(result.forbidden_collision_count, 0)
        self.assertGreaterEqual(result.minimum_body_clearance_m, 0.05)
```

- [ ] **Step 2: Verify normal/recovery fail at the conveyor and intervention fails at the visible obstacle**

- [ ] **Step 3: Add a pre-alignment waypoint, perform yaw alignment outside the keepout, and approach straight**

The final approach must keep `yaw_deg == -6.0` and move only along conveyor-local X.

- [ ] **Step 4: Shorten intervention precision approach so the vehicle stops before the obstacle while retaining the existing perception/Fallback event sequence**

- [ ] **Step 5: Certify every generated timeline before returning it**

Run: `PYTHONPATH=demo python3 -m unittest tests.test_timeline -v`

Expected: zero forbidden collisions in every scenario.

### Task 4: Runtime fail-closed guard and formal evidence

**Files:**
- Modify: `demo/seer_demo/isaac/runner.py`
- Modify: `demo/seer_demo/isaac/scene.py`
- Modify: `demo/seer_demo/presentation.py`
- Modify: `tests/test_timeline.py`
- Modify: `tests/test_presentation.py`

**Interfaces:**
- Produces summary keys `collision_guard`, `collision_check_count`, `minimum_body_clearance_m`, `maximum_allowed_contact_error_m`, `forbidden_collision_count`.
- Consumes `certify_timeline()` and per-frame guard functions.

- [ ] **Step 1: Write failing tests that reject a forged colliding timeline and require collision fields in presentation snapshots**

- [ ] **Step 2: Verify RED against the current runner/presentation behavior**

- [ ] **Step 3: Run certification before scene creation and re-check each frame before `apply_frame()`**

- [ ] **Step 4: Add certification fields to summary and the right-side safety panel without claiming full dynamics**

- [ ] **Step 5: Run timeline, presentation, contracts, and engine tests**

Run: `PYTHONPATH=demo python3 -m unittest tests.test_timeline tests.test_presentation tests.test_contracts tests.test_engine -v`

### Task 5: Formal render, visual audit, and publication

**Files:**
- Modify: `demo/evidence/isaac-*/events.jsonl`
- Modify: `demo/evidence/isaac-*/summary.json`
- Modify: `demo/evidence/isaac-*/scene.usda`
- Modify: `demo/evidence/isaac-*/simulation.mp4`
- Modify: `demo/evidence/isaac-*/presentation.mp4`
- Modify: `demo/evidence/MANIFEST.json`
- Modify: `demo/README.md`
- Modify: `demo/CLAIMS.md`
- Modify: `demo/项目总结与交付说明.md`
- Modify: `进度记录.md`

**Interfaces:**
- Consumes the completed collision-safe renderer.
- Produces the public, hash-verified three-scenario evidence set.

- [ ] **Step 1: Run all non-network tests with warnings as errors and JavaScript protocol tests**

- [ ] **Step 2: Render normal, recovery, and intervention in Isaac Sim 6.0.1 using new run directories**

- [ ] **Step 3: Build split-screen videos and regenerate `MANIFEST.json`**

- [ ] **Step 4: Extract contact sheets at entrance, insertion, lift, turn, conveyor approach, release, and safety stop**

- [ ] **Step 5: Verify video metadata, collision summary fields, event semantics, hashes, and browser playback**

- [ ] **Step 6: Update documentation with exact frame counts/durations and the simplified-physics boundary**

- [ ] **Step 7: Run secret scan, `git diff --check`, commit, push `feature/seer-hvla-demo`, and update PR #1**
