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

print("protocol assertions: " + assertions);
