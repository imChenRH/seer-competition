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
      durationS: eventDisplayTime(terminal),
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

  function eventDisplayTime(event) {
    if (!event) return null;
    return typeof event.display_time_s === "number"
      ? event.display_time_s
      : event.sim_time_s;
  }

  function projectEventTimes(events, fps) {
    validateEvents(events);
    const hasObservedFrames = events.some(function (event) {
      const frame = event.evidence && event.evidence.observed_frame;
      return Number.isInteger(frame) && frame >= 0;
    });
    if (hasObservedFrames && (typeof fps !== "number" || !Number.isFinite(fps) || fps <= 0)) {
      throw new Error("视频帧率必须是正数");
    }
    let previousTime = 0;
    return events.map(function (event) {
      const frame = event.evidence && event.evidence.observed_frame;
      let observedTime = previousTime;
      if (hasObservedFrames) {
        observedTime = Number.isInteger(frame) && frame >= 0
          ? frame / fps
          : previousTime;
      } else if (typeof event.sim_time_s === "number" && Number.isFinite(event.sim_time_s)) {
        observedTime = event.sim_time_s;
      }
      const displayTime = Math.max(previousTime, observedTime);
      previousTime = displayTime;
      return Object.freeze(Object.assign({}, event, {display_time_s: displayTime}));
    });
  }

  function chooseDefaultRun(runs) {
    if (!Array.isArray(runs) || runs.length === 0) {
      throw new Error("没有通过校验的证据运行");
    }
    return runs.find(function (run) {
      return run && run.scenario === "normal" && run.source === "isaac_sim";
    }) || runs[0];
  }

  function eventAtTime(events, simTimeS) {
    if (!Array.isArray(events) || typeof simTimeS !== "number") return null;
    let current = null;
    events.some(function (event) {
      const eventTime = eventDisplayTime(event);
      if (!event || typeof eventTime !== "number" || eventTime > simTimeS) {
        return true;
      }
      current = event;
      return false;
    });
    return current;
  }

  function dispatchPlan(events) {
    if (!Array.isArray(events)) return [];
    return events.filter(function (event) {
      return event && (event.event_type === "skill_started" || event.event_type === "fallback_started");
    }).map(function (event) {
      return Object.freeze({
        sequence: event.sequence,
        simTimeS: eventDisplayTime(event),
        kind: event.event_type === "fallback_started" ? "fallback" : "skill",
        identifier: event.fallback_id || event.skill_id,
        layer: "cerebellum",
        message: event.message || ""
      });
    });
  }

  function nextConsoleState(state, action) {
    const allowed = new Set(["normal", "recovery", "intervention", "fastwam"]);
    if (!action || typeof action.type !== "string") throw new Error("控制台动作无效");
    if (action.type === "initialize" || action.type === "select") {
      if (!allowed.has(action.scenario)) throw new Error("未知演示模式");
      return Object.freeze({selectedScenario: action.scenario, detailView: "hidden"});
    }
    if (action.type === "dispatch") {
      if (!state || !allowed.has(state.selectedScenario)) throw new Error("尚未选择演示模式");
      return Object.freeze({
        selectedScenario: state.selectedScenario,
        detailView: state.selectedScenario === "fastwam" ? "fastwam" : "evidence"
      });
    }
    throw new Error("未知控制台动作");
  }

  function reconcileTask(requested, recorded) {
    if (typeof requested !== "string" || typeof recorded !== "string" || !recorded.trim()) {
      throw new Error("任务文本无效");
    }
    return Object.freeze({accepted: requested.trim() === recorded.trim(), task: recorded.trim()});
  }

  function scrollOptions(prefersReducedMotion) {
    return Object.freeze({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "start"
    });
  }

  global.SeerProtocol = Object.freeze({
    chooseDefaultRun: chooseDefaultRun,
    dispatchPlan: dispatchPlan,
    eventDisplayTime: eventDisplayTime,
    eventAtTime: eventAtTime,
    nextConsoleState: nextConsoleState,
    projectEventTimes: projectEventTimes,
    reconcileTask: reconcileTask,
    scrollOptions: scrollOptions,
    validateEvents: validateEvents,
    reduceEvents: reduceEvents
  });
})(this);
