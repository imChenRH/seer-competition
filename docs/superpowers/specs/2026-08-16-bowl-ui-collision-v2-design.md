# Bowl Demo, Unified Presentation, and Intervention Geometry V2 Design

## Decision

Implement one evidence-versioned upgrade with three bounded changes:

1. replace the custom red-apple/yellow-plate Fast-WAM transfer with the canonical LIBERO `put_the_bowl_on_the_plate` task;
2. render and display Fast-WAM through the same TASK / BRAIN / CEREBELLUM / SAFETY / AUDIT presentation system used by the three forklift scenarios;
3. replace the hand-authored overlapping intervention boxes with shared, non-interpenetrating obstacle geometry used by both USD authoring and the collision certificate.

The canonical task is the recommended route because the checkpoint, language prompt, objects, initial states, and success predicate return to the model's training domain. A custom bowl with the yellow plate would retain an avoidable visual/geometry shift. Changing only action chunk length would not satisfy the requested object replacement and could hide the primary domain mismatch.

## Goals

- Make the recorded Fast-WAM task a real bowl-on-plate rollout controlled only by a repository/revision/SHA-bound checkpoint's 7-D actions.
- Improve measured five-initial-state success above the current apple result of 2/5 without hiding failed attempts.
- Give Fast-WAM the same split-video hierarchy, typography, card positions, state colors, and audit semantics as normal/recovery/intervention.
- Give Fast-WAM the same web evidence layout: summary metrics, video beside skill chain, lower evidence cards, and audit log.
- Remove visible obstacle/obstacle penetration from the safety-intervention source video and certify the exact authored obstacle geometry.

## Non-Goals

- No Fast-WAM forklift control, ROS 2 integration, real-hardware claim, or production-safety claim.
- No rule controller may replace or supplement Fast-WAM actions after rollout starts.
- No enlargement of the target or relaxation of the official LIBERO success predicate.
- No editing of old videos to conceal geometry; the intervention source scene must be rerendered.
- No hidden reasoning text. The right panel contains only task mapping, dispatch labels, actions, observations, gates, and audit events.

## Fast-WAM Task and Evidence Contract

The rollout wrapper will use canonical suite `libero_goal`, task id `8`, task name `put_the_bowl_on_the_plate`, the task's original BDDL, original assets, and original two 224×224 cameras. The physical state adapter observes `akita_black_bowl_1` and `plate_1`. The scenario identifier becomes `fastwam_bowl_plate`; user-facing instructions become `把黑色碗放入盘子`.

Five fixed official initial states (`episode_index` 0 through 4) are executed with deterministic seeds. The first evaluation uses the official 300-step budget. Publication requires a measured result strictly better than 2/5; if that gate fails, diagnostics may change policy replanning frequency or episode budget, but every deviation must be explicit in `summary.json`, and no rule action may be introduced. All five videos, actions, and states remain in the evidence package.

The successful event trace retains the eight existing ARM/WAM skills. State fields are renamed from `apple_*` to `bowl_*`. A run is successful only when the unmodified environment reports `env.check_success()`.

## Common Split-Video Presentation

`seer_demo.presentation.render_overlay(...)` remains the sole visual layout. A source adapter supplies a common presentation snapshot:

- `goal`, `status`, `scenario`, and current skill;
- `brain.mode`, `brain.dispatch`, and structured intent;
- `cerebellum.controller` plus a source-specific list of visible metrics;
- `safety.gate` plus source-specific observable checks;
- the latest three audit events.

Forklift adapters continue to emit base, mast, fork, payload, collision, and stop metrics. The Fast-WAM adapter emits 7-D action summary, bowl lift, plate XY error, gripper state, model-call marker, latency, official predicate, and five-attempt result. The right half uses exactly the same card rectangles, fonts, theme colors, headings, and audit rows as the forklift presentation. Source-specific text changes only the left header and card contents.

The presentation remains 2560×1080 with a 1280×720 source video at `(0, 180)`, identical frame count/fps to its source, and an observation-bound event clock.

## Unified Web Console

All four tabs use the existing `#evidence-content` DOM. Fast-WAM no longer switches to a separate `#fastwam-content` page. Its dispatch handler populates:

- the four standard metric cards;
- the standard video player and phase track;
- the standard skill-chain card;
- a dynamically titled lower-left card containing official predicate, current 7-D action, and five fixed-state results;
- the standard continuous audit log.

The Fast-WAM tab, preset, hero copy, badges, labels, and accessibility text use bowl/plate terminology. Atomic fetch/generation guards remain unchanged, and invalid evidence fails closed before any DOM commit.

## Intervention Obstacle Geometry

Introduce `intervention_obstacle_geometry_specs()` in `isaac/layout.py`. It returns two floor-supported boxes with a positive horizontal gap and no Z penetration. `isaac/scene.py` and `isaac/collision.py` consume this exact function; neither may duplicate sizes or offsets.

Add a static-geometry certificate that checks:

- every obstacle bottom is at or above the container floor;
- no two active obstacle OBBs overlap in XY and Z;
- obstacle names are unique;
- the obstacle group remains in the intended occlusion region;
- forklift swept collision and contact certificates remain zero-violation.

The formal intervention run is rerendered from the corrected USD scene. Its summary records `obstacle_interpenetration_count: 0` and the manifest hashes the new source video, scene, events, summary, and split presentation.

## Error Handling

- Reject a task-id/name mismatch before loading policy weights.
- Reject missing canonical bowl/plate bodies immediately after reset.
- Reject malformed/nonfinite action or physical-state fields as before.
- Reject a presentation snapshot that lacks the common schema.
- Reject obstacle specs that touch by penetration rather than a bounded nonnegative gap.
- Never publish a bowl result if five attempts, source media, event trace, or manifest hashes are incomplete.

## Testing and Acceptance

- Static scene tests prove canonical BDDL/assets are not overridden and bowl/plate bodies are observed.
- Contract tests reject apple scenario IDs/fields in the new formal package.
- Presentation tests compare Fast-WAM and forklift card geometry, headings, theme transitions, and audit locations.
- Web protocol tests prove Fast-WAM uses the standard evidence workspace and no separate active content path.
- Geometry tests reproduce the current two-box overlap before the fix and require zero overlap afterward.
- All Python tests, JavaScript protocol assertions, `compileall`, shell syntax, `git diff --check`, manifest rebuild, ffprobe checks, and local HTTP/Range requests pass.
- Visual QA contact sheets confirm a canonical bowl, common right-panel layout, common web layout, and separated intervention obstacles.

## Delivery

Work on branch `feature/bowl-ui-collision-v2` based on `origin/master` commit `14c918835d2507555f877874a95c5b1300ddfb48`. Publish new evidence under versioned bowl and intervention run directories, update claims/report/progress documents, push to the public fork, open a draft PR against `imChenRH/master`, and deploy the exact final commit to local port `8766`.
