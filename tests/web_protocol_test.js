load("demo/web/protocol.js");

let assertions = 0;
function assert(condition, message) {
  assertions += 1;
  if (!condition) throw new Error(message);
}
function event(sequence, type, extra) {
  return Object.assign({
    schema_version: "1.0",
    run_id: "run-1",
    sequence: sequence,
    scenario: "recovery",
    event_type: type,
    source: "isaac_sim",
    sim_time_s: sequence,
    status: "RUNNING",
    occurred_at: "2026-08-13T00:00:00Z",
    skill_id: null,
    fallback_id: null,
    state: {},
    evidence: {}
  }, extra || {});
}

const valid = [
  event(0, "task_started"),
  event(1, "skill_completed", {skill_id: "FORK-NAV-01"}),
  event(2, "fallback_started", {fallback_id: "FB-F01", status: "FALLBACK"}),
  event(3, "skill_completed", {skill_id: "FORK-PER-01"}),
  event(4, "task_completed", {status: "COMPLETED", sim_time_s: 62})
];

assert(SeerProtocol.validateEvents(valid).runId === "run-1", "valid run id");
assert(SeerProtocol.validateEvents(valid).terminalStatus === "COMPLETED", "terminal");
const reduced = SeerProtocol.reduceEvents(valid);
assert(reduced.completedSkills.length === 2, "skill count");
assert(reduced.fallbackCount === 1, "fallback count");
assert(reduced.durationS === 62, "duration from event");
assert(reduced.source === "isaac_sim", "source from event");
assert(reduced.eventCount === 5, "event count from batch");

let rejected = 0;
for (const broken of [
  [valid[0], Object.assign({}, valid[1], {sequence: 3}), valid[4]],
  [valid[0], Object.assign({}, valid[1], {run_id: "other"}), valid[4]],
  [valid[0], Object.assign({}, valid[1], {event_type: "task_completed", status: "COMPLETED"}), valid[2]],
  [],
]) {
  try { SeerProtocol.validateEvents(broken); } catch (_) { rejected += 1; }
}
assert(rejected === 4, "four invalid batches rejected");
assert(valid[0].sequence === 0, "input is not mutated");
assert(reduced.terminalStatus === "COMPLETED", "reducer terminal");
assert(reduced.scenario === "recovery", "reducer scenario");
assert(reduced.runId === "run-1", "reducer run id");
const runs = [
  {run_id: "intervention-latest", scenario: "intervention", source: "isaac_sim"},
  {run_id: "normal-dry", scenario: "normal", source: "dry_run"},
  {run_id: "normal-formal", scenario: "normal", source: "isaac_sim"}
];
assert(SeerProtocol.chooseDefaultRun(runs).run_id === "normal-formal", "formal normal is default");
assert(SeerProtocol.chooseDefaultRun([runs[0]]).run_id === "intervention-latest", "first run fallback");
assert(SeerProtocol.eventAtTime(valid, 0).event_type === "task_started", "zero-time event");
assert(SeerProtocol.eventAtTime(valid, 2.9).fallback_id === "FB-F01", "latest event at time");
assert(SeerProtocol.eventAtTime(valid, -1) === null, "no event before timeline");
const projected = SeerProtocol.projectEventTimes([
  Object.assign({}, valid[0], {evidence: {observed_frame: 0}}),
  Object.assign({}, valid[1], {evidence: {observed_frame: 80}}),
  Object.assign({}, valid[2], {evidence: {}}),
  Object.assign({}, valid[3], {evidence: {observed_frame: 160}}),
  Object.assign({}, valid[4], {evidence: {observed_frame: 528}})
], 8);
assert(projected.length === 5, "clock projection preserves event count");
assert(projected[1].display_time_s === 10, "observed frame projects to video time");
assert(projected[2].display_time_s === 10, "unobserved start inherits prior boundary");
assert(projected[4].display_time_s === 66, "terminal remains aligned to final video observation");
assert(SeerProtocol.eventAtTime(projected, 10).fallback_id === "FB-F01", "playback uses projected clock");
assert(SeerProtocol.dispatchPlan(projected)[0].simTimeS === 10, "dispatch plan uses projected clock");
assert(valid[1].display_time_s === undefined, "clock projection does not mutate evidence");
const dryProjected = SeerProtocol.projectEventTimes(valid, Number.NaN);
assert(dryProjected[4].display_time_s === 62, "dry-run projection preserves simulation time");
let badObservedFpsRejected = false;
try { SeerProtocol.projectEventTimes(projected, 0); } catch (_) { badObservedFpsRejected = true; }
assert(badObservedFpsRejected, "observed frames require a positive video frame rate");
assert(SeerProtocol.scrollOptions(false).behavior === "smooth", "normal dispatch scrolls smoothly");
assert(SeerProtocol.scrollOptions(true).behavior === "auto", "reduced motion disables smooth scroll");
const dispatch = SeerProtocol.dispatchPlan(valid);
assert(dispatch.length === 1, "dispatch plan uses started actions only");
assert(dispatch[0].identifier === "FB-F01", "fallback dispatch identifier");
assert(dispatch[0].layer === "cerebellum", "dispatch layer is explicit");

let consoleState = SeerProtocol.nextConsoleState(null, {type: "initialize", scenario: "normal"});
assert(consoleState.selectedScenario === "normal", "initial scenario");
assert(consoleState.detailView === "hidden", "initial detail hidden");
consoleState = SeerProtocol.nextConsoleState(consoleState, {type: "select", scenario: "recovery"});
assert(consoleState.selectedScenario === "recovery", "selection changes scenario");
assert(consoleState.detailView === "hidden", "selection collapses prior evidence");
consoleState = SeerProtocol.nextConsoleState(consoleState, {type: "dispatch"});
assert(consoleState.detailView === "evidence", "recorded scenario dispatch reveals evidence");
consoleState = SeerProtocol.nextConsoleState(consoleState, {type: "select", scenario: "fastwam"});
assert(consoleState.detailView === "hidden", "fastwam selection is also gated");
consoleState = SeerProtocol.nextConsoleState(consoleState, {type: "dispatch"});
assert(consoleState.detailView === "fastwam", "fastwam dispatch reveals independent proof");
assert(SeerProtocol.reconcileTask("  recorded task ", "recorded task").accepted, "matching task is accepted");
const rejectedTask = SeerProtocol.reconcileTask("invented task", "recorded task");
assert(!rejectedTask.accepted && rejectedTask.task === "recorded task", "unrecorded task falls back to evidence task");

const fastEvents = [
  event(0, "task_started", {run_id: "wam-1", scenario: "fastwam_apple_plate", source: "fastwam_policy", evidence: {observed_frame: 0}}),
  event(1, "skill_started", {run_id: "wam-1", scenario: "fastwam_apple_plate", source: "fastwam_policy", skill_id: "ARM-OP-01", evidence: {observed_frame: 1}}),
  event(2, "skill_completed", {run_id: "wam-1", scenario: "fastwam_apple_plate", source: "fastwam_policy", skill_id: "ARM-VER-01", state: {official_success: true}, evidence: {observed_frame: 2}}),
  event(3, "task_completed", {run_id: "wam-1", scenario: "fastwam_apple_plate", source: "fastwam_policy", status: "COMPLETED", state: {official_success: true}, evidence: {observed_frame: 3}})
];
const fastActions = [
  {schema_version: "1.0", run_id: "wam-1", sequence: 0, observed_frame: 1, sim_time_s: 0.05, action: [0, 0, 0, 0, 0, 0, -1], model_call: true, latency_s: 0.22},
  {schema_version: "1.0", run_id: "wam-1", sequence: 1, observed_frame: 2, sim_time_s: 0.10, action: [0.1, 0, 0, 0, 0, 0, 1], model_call: false, latency_s: 0.001}
];
const fastSummary = {
  run_id: "wam-1", scenario: "fastwam_apple_plate", source: "fastwam_policy",
  frame_count: 4, action_count: 2, policy_call_count: 1,
  terminal_status: "COMPLETED", official_success: true, selected_attempt: 2,
  attempts: [0, 1, 2, 3, 4].map(function (index) { return {attempt_index: index, success: index === 2}; })
};
assert(SeerProtocol.validateFastWamEvidence(fastSummary, fastEvents, fastActions).runId === "wam-1", "fastwam evidence validates atomically");
assert(SeerProtocol.fastWamAtFrame(fastEvents, fastActions, 0).action === null, "no action before observed frame");
assert(SeerProtocol.fastWamAtFrame(fastEvents, fastActions, 2).action.sequence === 1, "latest observed action selected");
assert(SeerProtocol.fastWamAtFrame(fastEvents, fastActions, 2).event.sequence === 2, "latest observed event selected");
assert(SeerProtocol.fastWamFrame(0.149, 20, 4) === 2, "playback time floors to source frame");

let invalidFastWam = 0;
for (const brokenActions of [
  [Object.assign({}, fastActions[0], {action: [0, 0, 0, 0, 0, 0]})],
  [Object.assign({}, fastActions[0], {run_id: "other"})],
  [Object.assign({}, fastActions[0], {sequence: 2})],
  [Object.assign({}, fastActions[0], {observed_frame: 4})],
  [Object.assign({}, fastActions[0], {action: [0, 0, 0, 0, 0, 0, Number.NaN]})]
]) {
  try { SeerProtocol.validateFastWamEvidence(Object.assign({}, fastSummary, {action_count: brokenActions.length}), fastEvents, brokenActions); } catch (_) { invalidFastWam += 1; }
}
assert(invalidFastWam === 5, "malformed fastwam actions fail closed");
let forgedFastSuccessRejected = false;
try { SeerProtocol.validateFastWamEvidence(Object.assign({}, fastSummary, {official_success: false}), fastEvents, fastActions); } catch (_) { forgedFastSuccessRejected = true; }
assert(forgedFastSuccessRejected, "fastwam summary cannot contradict terminal predicate");
assert(fastActions[0].action.length === 7, "fastwam validator does not mutate action evidence");

print("protocol assertions: " + assertions);
