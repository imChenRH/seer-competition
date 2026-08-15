# Demo Visual and Physics V2 Design

Date: 2026-08-16
Status: approved
Decision: local refactor; retain the task engine, scenarios, audit contracts, and evidence pipeline

## Goal

Improve the SEER-HVLA enterprise demo without replacing its verified architecture. The revised demo must show a grounded forklift, a larger shipping container, physically coherent conveyor support, wider subject-safe camera framing, clearer right-side decision-state changes, and a roomier synchronized web presentation.

## Scope

The change keeps:

- the normal, recovery, and intervention scenarios;
- AgentOS skill dispatch and fallback semantics;
- event ordering, validation, and audit continuity;
- explicit fixed-joint payload attachment during transport;
- the raw-video, presentation-video, summary, and manifest evidence pipeline.

The change replaces or revises:

- forklift wheel geometry and ground-contact dimensions;
- container dimensions, facility headings, targets, and affected routes;
- conveyor geometry and payload release support behavior;
- phase camera selection with subject-aware framing;
- presentation overlay visual states and event clock use;
- web evidence layout, dispatch scrolling, playback clock, and mock sidebar.

## Physical design

### Forklift

The current wheel parts are boxes whose lowest points are approximately 0.20–0.21 m above the ground. V2 uses cylinder geometry for all four wheels. The wheel center is exactly one radius above the ground plane, and the forklift root remains at world Z=0 for all timeline frames.

Acceptance:

- each wheel-ground distance is within 0.002 m in every authored frame;
- no wheel penetrates the ground by more than 0.001 m;
- the chassis stays above the ground and the forklift root never receives lift animation.

### Container and facility alignment

The shipping container, not the active cargo, grows from approximately 6.0 x 2.8 x 3.0 m to 7.5 x 3.4 x 3.5 m. Targets and background loads remain inside its collision envelope. A single lane-heading constant defines the world-X yellow-line direction. Both the container and conveyor use that heading.

Acceptance:

- container dimensions meet or exceed 7.5 x 3.4 x 3.5 m;
- container and conveyor headings equal the yellow lane heading;
- pickup, exit, and placement routes remain collision-certified.

### Conveyor

V2 is a roller conveyor, not a collection of small support cubes. It has cylindrical cross-width rollers, side beams, cross-members, legs, and a well-defined support height. Static members have collision and metal physics material. Fork pockets remain reachable during withdrawal.

The forklift and carried payload stay kinematic for reproducible approach and transport. The fixed joint is disabled at placement. The released payload receives a bounded settling interval on the conveyor support, and completion requires support-height, contact, and near-zero-motion evidence. The demo does not claim powered downstream conveying.

## Camera design

Phase presets continue to choose useful viewing angles, but each frame derives its target and distance from the forklift plus attached-payload bounds. The camera may move farther away but may not crop the subject.

Acceptance:

- the projected forklift bounds remain inside a 5% frame-safe margin;
- attached payload bounds are included;
- camera transitions are interpolated rather than discontinuous;
- the warehouse context remains visible at pickup, transport, placement, and stop phases.

## Presentation design

The split remains raw Isaac footage on the left and structured brain/cerebellum evidence on the right. The right side shows verifiable decision summaries, not hidden chain-of-thought.

State themes:

- planning/running: blue;
- completed: green;
- fallback/recovery: amber;
- safety stop/human handoff: red.

The active state changes card fill, accent, title, status badge, and primary instruction typography. The primary dispatch is substantially larger than supporting metrics. Overlay state changes and the web playback cursor use observed frame time when available, preventing the decision view from finishing before the source video.

## Web design

At the meeting desktop viewport, the evidence workspace uses approximately 74% for video and 26% for the skill chain while remaining side by side. After a successful dispatch, the page reveals the selected evidence, scrolls its video section into view, resets playback, and starts replay. Reduced-motion users receive an immediate rather than animated scroll.

The entire mock Feishu sidebar is removed from the DOM and its space is returned to the conversation.

## Evidence and truth boundary

All three Isaac scenarios must be rerendered. Existing videos and manifests become stale after geometry, timing, or camera changes and must not be reused. Final evidence must bind events, summary, raw video, presentation video, collision certification, and hashes from one run.

## Non-goals

- production forklift dynamics, tire forces, or steering calibration;
- autonomous powered conveyor motion;
- real perception or real robot control;
- unlogged model reasoning or fabricated live planning.
