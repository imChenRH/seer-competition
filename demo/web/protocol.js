(function (global) {
  "use strict";

  const terminalTypes = new Set([
    "task_completed",
    "task_failed",
    "human_intervention_requested"
  ]);

  function validateEvents(events) {
    if (!Array.isArray(events) || events.length === 0) {
      throw new Error("事件批次不能为空");
    }
    const first = events[0];
    let previousTime = -1;
    let terminalIndex = -1;
    events.forEach(function (event, index) {
      if (!event || !Number.isInteger(event.sequence) || event.sequence !== index) {
        throw new Error("事件序号不连续: expected " + index);
      }
      if (event.run_id !== first.run_id || event.scenario !== first.scenario) {
        throw new Error("事件批次混入其他运行");
      }
      if (typeof event.sim_time_s !== "number" || event.sim_time_s < previousTime) {
        throw new Error("仿真时间不是单调序列");
      }
      previousTime = event.sim_time_s;
      if (terminalTypes.has(event.event_type)) {
        if (terminalIndex !== -1) throw new Error("存在多个终态事件");
        terminalIndex = index;
      }
    });
    if (terminalIndex !== events.length - 1) {
      throw new Error("终态事件必须存在且位于末尾");
    }
    return {
      runId: first.run_id,
      scenario: first.scenario,
      source: first.source,
      terminalStatus: events[terminalIndex].status
    };
  }

  function reduceEvents(events) {
    const validation = validateEvents(events);
    const terminal = events[events.length - 1];
    return {
      runId: validation.runId,
      scenario: validation.scenario,
      source: validation.source,
      terminalStatus: validation.terminalStatus,
      eventCount: events.length,
      durationS: terminal.sim_time_s,
      completedSkills: events
        .filter(function (event) { return event.event_type === "skill_completed"; })
        .map(function (event) { return event.skill_id; }),
      fallbackCount: events.filter(function (event) {
        return event.event_type === "fallback_started";
      }).length,
      safetyStopCount: events.filter(function (event) {
        return event.event_type === "safety_stop";
      }).length
    };
  }

  function chooseDefaultRun(runs) {
    if (!Array.isArray(runs) || runs.length === 0) {
      throw new Error("没有通过校验的证据运行");
    }
    return runs.find(function (run) {
      return run && run.scenario === "normal" && run.source === "isaac_sim";
    }) || runs[0];
  }

  global.SeerProtocol = Object.freeze({
    chooseDefaultRun: chooseDefaultRun,
    validateEvents: validateEvents,
    reduceEvents: reduceEvents
  });
})(this);
