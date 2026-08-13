# SEER–HVLA Demo Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver a reproducible, evidence-driven SEER forklift Demo whose Mac dry-run, AutoDL Isaac run, Feishu bridge, dashboard, videos, and claims all agree.

**Architecture:** A pure-Python event contract and scenario engine own task truth. Dry-run and Isaac backends execute the same scenario definition; the Feishu bridge invokes a runner once and consumes its JSONL; the dashboard only renders validated JSONL and linked media.

**Tech Stack:** Python 3.10+ standard library, `unittest`, Isaac Sim 6.0.1 Python runtime, OpenUSD/Replicator, HTML/CSS/vanilla JavaScript, FFmpeg.

## Global Constraints

- Preserve the 13-skill and 10-Fallback identifiers already configured in Aily.
- Formal forklift execution is deterministic rule control; Fast-WAM stays an independent verification track.
- Never commit `.env`, `凭证汇总.md`, access tokens, passwords, private keys, or Feishu record contents containing secrets.
- Never label dry-run as simulation, kinematic Isaac execution as hardware control, or the paper's 190 ms as a measured local result.
- A task runner is launched exactly once per claimed task.
- JSONL sequence numbers start at 0, contain no gaps, and have one terminal event.

---

### Task 1: Event Contract and Evidence Validation

**Files:**
- Create: `demo/seer_demo/__init__.py`
- Create: `demo/seer_demo/contracts.py`
- Create: `tests/test_contracts.py`

**Interfaces:**
- Produces: `Event`, `EventWriter`, `load_events(path)`, and `validate_events(events, expected_scenario=None)`.

- [x] **Step 1: Write failing contract tests** for contiguous sequence numbers, monotonic simulation time, a single terminal event, matching run IDs, and rejection of events after terminal.
- [x] **Step 2: Run** `python3 -m unittest tests.test_contracts -v` and confirm failures are caused by missing production imports.
- [x] **Step 3: Implement immutable event serialization and validation** with literal allowed source/status/event sets and actionable `ValueError` messages.
- [x] **Step 4: Run** `python3 -m unittest tests.test_contracts -v` and confirm all contract tests pass.

### Task 2: Scenario Engine and Three Truthful Outcomes

**Files:**
- Create: `demo/seer_demo/scenarios.py`
- Create: `demo/seer_demo/engine.py`
- Create: `demo/seer_demo/backends/__init__.py`
- Create: `demo/seer_demo/backends/dry_run.py`
- Create: `demo/seer_demo/cli.py`
- Create: `tests/test_engine.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `EventWriter`.
- Produces: `ScenarioDefinition`, `DemoEngine.run(scenario)`, `DryRunBackend`, and `python -m seer_demo.cli run|validate`.

- [x] **Step 1: Write failing engine tests** asserting the exact nine-skill normal sequence, `FB-F01` recovery followed by completion, and `FB-F02 → FB-F07` followed by `HUMAN_REQUIRED`.
- [x] **Step 2: Run** `PYTHONPATH=demo python3 -m unittest tests.test_engine tests.test_cli -v` and confirm expected missing behavior.
- [x] **Step 3: Implement the smallest deterministic state machine** that emits observable backend state for every completed skill and never advances on a failed action.
- [x] **Step 4: Implement CLI run and validate commands**; `run` writes JSONL and a summary JSON, and names dry-run evidence honestly.
- [x] **Step 5: Run focused tests and then** `PYTHONPATH=demo python3 -m unittest discover -s tests -v`.

### Task 3: One-Shot, Idempotent Feishu Bridge

**Files:**
- Create: `demo/seer_demo/feishu.py`
- Create: `demo/seer_demo/bridge.py`
- Create: `demo/.env.example`
- Create: `tests/test_bridge.py`

**Interfaces:**
- Consumes: runner JSONL events.
- Produces: `FeishuClient`, `TaskBridge.process_once()`, `RunnerProcess.run(task) -> Iterable[Event]`.

- [x] **Step 1: Write failing tests** with an in-memory Feishu boundary proving compare-and-set claim, one runner invocation for nine skills, one update per event sequence, no duplicate replay, nonzero runner exit mapped to `异常`, and malformed JSONL mapped to fail-closed.
- [x] **Step 2: Run** `PYTHONPATH=demo python3 -m unittest tests.test_bridge -v` and confirm failure for missing bridge.
- [x] **Step 3: Implement `urllib` Feishu calls, token caching, pagination and injected transport**; production secrets are read only from environment or ignored `.env`.
- [x] **Step 4: Implement bridge claim/run/update flow** with a stored `last_event_sequence` and no per-skill subprocess loop.
- [x] **Step 5: Run focused and full local tests**.

### Task 4: Isaac Z-up Scene and Synchronized Runner

**Files:**
- Create: `demo/seer_demo/isaac/__init__.py`
- Create: `demo/seer_demo/isaac/scene.py`
- Create: `demo/seer_demo/isaac/runner.py`
- Create: `demo/seer_demo/isaac/timeline.py`
- Create: `tests/test_timeline.py`
- Create: `scripts/run_isaac_demo.sh`

**Interfaces:**
- Consumes: scenario definitions and timeline keyframes.
- Produces: a saved Z-up USD, per-frame vehicle/load state, JSONL, frame directory, summary, and encoded MP4.

- [x] **Step 1: Write failing pure-Python timeline tests** for Z-up coordinates, local child transforms, monotonic frame times, normal payload coupling/release, recovery lateral correction, and intervention safe-stop immobility.
- [x] **Step 2: Run** `PYTHONPATH=demo python3 -m unittest tests.test_timeline -v` and confirm expected failures.
- [x] **Step 3: Implement scenario timelines** independently of Isaac imports so Mac tests exercise the real trajectory data.
- [x] **Step 4: Implement Isaac scene construction** with correct Z-up geometry, visual safety zones, container, conveyor, locally modeled forklift, pallet/load and scenario obstacle.
- [x] **Step 5: Implement runner/recorder** that applies timeline states, couples the payload only after pickup, releases only at the conveyor, writes events from observed state, and uses FFmpeg to encode.
- [x] **Step 6: Upload the tracked package to AutoDL, execute all three scenarios, download outputs, and validate each JSONL locally.**

### Task 5: Evidence-Backed Web Console

**Files:**
- Create: `demo/seer_demo/server.py`
- Create: `demo/web/index.html`
- Create: `demo/web/styles.css`
- Create: `demo/web/app.js`
- Create: `tests/test_server.py`
- Create: `tests/test_web_protocol.py`

**Interfaces:**
- Consumes: validated summaries, JSONL and MP4 by run ID.
- Produces: `python -m seer_demo.cli serve` and `/api/runs`, `/api/runs/{id}`, `/api/runs/{id}/events`.

- [x] **Step 1: Write failing HTTP tests** for path allow-listing, JSON content types, missing run 404, and refusal to serve files outside the evidence root.
- [x] **Step 2: Write a JavaScript protocol fixture** that rejects duplicate/gapped/cross-run events and computes counts from events rather than constants.
- [x] **Step 3: Implement the standard-library server and static console** with video, nine-skill timeline, Fallback/safety panel, evidence metadata, and explicit prototype limitations.
- [x] **Step 4: Run server tests, JavaScript syntax checking available on macOS, and a real local HTTP smoke test.**

### Task 6: Documentation, Claims Matrix and Operator Workflow

**Files:**
- Create: `demo/README.md`
- Create: `demo/AUDIT.md`
- Create: `demo/CLAIMS.md`
- Create: `scripts/run_demo.sh`
- Modify: `demo/Demo制作规划.md`
- Modify: `进度记录.md`
- Modify: `待办事项.md`

**Interfaces:**
- Produces: exact Mac and AutoDL commands, enterprise meeting flow, failure recovery, artifact paths, and claim/evidence/status mapping.

- [x] **Step 1: Document the audit findings** including the ninefold bridge execution and non-physical legacy Xform animation.
- [x] **Step 2: Write the claims matrix** with `VERIFIED`, `DEMO_IMPLEMENTED`, `PAPER_METRIC`, and `NOT_IMPLEMENTED` labels.
- [x] **Step 3: Replace stale planning/status text** so documents agree on Isaac 6.0.1, rule control, separate Fast-WAM validation, and actual evidence paths.
- [x] **Step 4: Add check/run scripts** that refuse missing dependencies, validate port numbers and never print credentials.

### Task 7: Final Verification and Delivery Gate

**Files:**
- Create: `demo/evidence/MANIFEST.json`
- Create: `demo/evidence/<run-id>/*.jsonl|*.json|*.mp4`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: every earlier deliverable.
- Produces: a clean, committed, reproducible Demo branch.

- [x] **Step 1: Run the complete local suite** with `PYTHONPATH=demo python3 -m unittest discover -s tests -v`.
- [x] **Step 2: Run all three dry-run scenarios and validate their JSONL.**
- [x] **Step 3: Validate the three downloaded Isaac JSONL files, MP4 duration/resolution/frame counts, and manifest SHA-256 values.**
- [x] **Step 4: Start the server, request its HTML/API/media routes, and verify the console renders one real run without hardcoded metrics.**
- [x] **Step 5: Run secret scans, Python compile, shell syntax checks, HTML/JS syntax checks, `git diff --check`, and confirm ignored credentials remain untracked.**
- [x] **Step 6: Re-read the design acceptance list, record evidence for every item, fix any gap, then commit the reviewed scope.**
