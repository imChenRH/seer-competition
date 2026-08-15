# Demo Visual and Physics V2 Implementation Plan

> Execute in `feature/demo-visual-physics-v2` with test-driven changes. Do not reuse old rendered evidence after scene or clock changes.

**Goal:** Deliver a grounded, collision-certified, fully framed warehouse demo with a larger aligned container, a coherent roller conveyor, more legible synchronized decision visuals, and an improved web evidence layout.

**Architecture:** Retain the deterministic AgentOS and evidence pipeline. Centralize physical dimensions and lane headings in the pure-Python geometry contract, derive timelines and collision envelopes from that contract, and make rendering and web presentation consume evidence-frame time.

**Technology:** Python 3, OpenUSD/Isaac Sim 6.0.1, Pillow/FFmpeg, vanilla HTML/CSS/JavaScript, unittest.

---

## Task 1: Ground-contact and facility contracts

**Files:**

- Modify: `tests/test_timeline.py`
- Modify: `demo/seer_demo/isaac/layout.py`
- Modify: `demo/seer_demo/isaac/timeline.py`

**Steps:**

1. Add failing tests for four wheel contact heights, wheel primitive roles, larger container bounds, and the shared yellow-lane heading.
2. Run the focused timeline tests and confirm failures name the old floating-wheel and counter-yaw behavior.
3. Add shared wheel and facility dimension contracts.
4. Recompute container-local targets and background-load positions.
5. Run focused tests and the collision certification tests.

## Task 2: Author real wheel and conveyor geometry

**Files:**

- Modify: `tests/test_timeline.py`
- Modify: `demo/seer_demo/isaac/layout.py`
- Modify: `demo/seer_demo/isaac/scene.py`
- Modify: `demo/seer_demo/isaac/collision.py`

**Steps:**

1. Add failing tests for cylindrical wheel/roller authoring, conveyor support height, open fork channels, and collision-role coverage.
2. Add typed cylinder geometry specs and scene authoring with the correct axis and material.
3. Replace cube rollers with cross-width cylinders plus side beams, cross-members, and legs.
4. Update static and allowed-contact collision envelopes from the same geometry source.
5. Run focused tests for geometry, collision, attachment, and payload support.

## Task 3: Release and settle contract

**Files:**

- Modify: `tests/test_timeline.py`
- Modify: `demo/seer_demo/isaac/timeline.py`
- Modify: `demo/seer_demo/isaac/scene.py`
- Modify: `demo/seer_demo/isaac/runner.py`
- Modify: `demo/seer_demo/contracts.py` only if evidence fields require a compatible extension

**Steps:**

1. Add failing tests that placement cannot complete while unsupported, moving, or intersecting the conveyor.
2. Add a bounded settle phase after fixed-joint release.
3. Record support/contact and near-zero-motion observations from the stage.
4. Preserve deterministic failure behavior if settle evidence is absent.
5. Run timeline, engine, and contract tests.

## Task 4: Subject-safe camera framing

**Files:**

- Modify: `tests/test_timeline.py`
- Modify: `demo/seer_demo/isaac/scene.py`
- Modify: `demo/seer_demo/isaac/runner.py`

**Steps:**

1. Add failing projection tests across every frame of all scenarios, including attached payload bounds.
2. Replace phase-only poses with phase angle presets plus per-frame subject target and fit distance.
3. Add interpolation at phase transitions and export the new camera-strategy identifier.
4. Verify the 5% safe-frame margin for all sampled bounds.

## Task 5: Make decision-state visuals unmistakable

**Files:**

- Modify: `tests/test_presentation.py`
- Modify: `demo/seer_demo/presentation.py`

**Steps:**

1. Add failing image-level tests for distinct running, completed, recovery, and safety themes.
2. Introduce a state-theme projection that controls card fill, accent, badge, and typography.
3. Increase current-dispatch and section font sizes while keeping long Chinese text bounded.
4. Verify that overlay event changes use observed-frame time and remain visible through the final video frame.
5. Render representative overlay PNGs for visual inspection.

## Task 6: Expand video and improve dispatch navigation

**Files:**

- Modify: `tests/test_web_protocol.py`
- Modify: `demo/web/index.html`
- Modify: `demo/web/styles.css`
- Modify: `demo/web/app.js`
- Modify: `demo/web/protocol.js`

**Steps:**

1. Add failing DOM/protocol tests for sidebar removal, the wider video column, evidence-frame time projection, and post-dispatch scrolling.
2. Remove the mock sidebar markup and reclaim its grid column.
3. Change the desktop workspace to a 74/26 video/skill-chain split.
4. Scroll the revealed evidence region into view after a successful dispatch, respecting reduced motion.
5. Use evidence-frame time for active web state and run JavaScriptCore protocol tests.

## Task 7: Full local verification

**Files:**

- Modify: `demo/README.md` if operation or truth-boundary text changed
- Modify: `demo/RUNBOOK.md` if rerender instructions changed

**Steps:**

1. Run focused Python and JavaScript tests after each task.
2. Run `./scripts/run_demo.sh check`.
3. Run all three dry-run scenarios and validate their event streams.
4. Run collision certification for normal, recovery, and intervention.
5. Run compile, shell syntax, JavaScript syntax, and `git diff --check` checks.

## Task 8: Rerender and bind formal evidence

**Files:**

- Replace: formal raw and presentation media under `demo/evidence/isaac-*`
- Replace: affected `summary.json`, collision evidence, and manifests
- Update: progress/summary documentation for the new run IDs

**Steps:**

1. Upload the exact branch commit to the configured Isaac Sim 6.0.1 host.
2. Render normal, recovery, and intervention at the formal resolution and FPS.
3. Build split presentation videos with a verified CJK font.
4. Download artifacts and regenerate manifests from the new runs.
5. Verify frame counts, durations, resolutions, hashes, event semantics, and final-state timing.
6. Produce contact sheets for wheel contact, container scale, camera coverage, conveyor placement, recovery, and safety stop.
7. Test the local browser dispatch and playback flow at the meeting viewport.

## Task 9: Review and publish

**Steps:**

1. Review the complete diff against this design and the nine user requirements.
2. Run fresh completion verification.
3. Commit in coherent units, push `feature/demo-visual-physics-v2`, and report the branch and evidence paths.
