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
        detailView: "evidence"
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

  function validateFastWamEvidence(summary, events, actions) {
    if (!summary || summary.source !== "fastwam_policy" || summary.scenario !== "fastwam_bowl_plate") {
      throw new Error("Fast-WAM 摘要来源或场景无效");
    }
    const eventValidation = validateEvents(events);
    if (eventValidation.runId !== summary.run_id || eventValidation.source !== summary.source) {
      throw new Error("Fast-WAM 事件与摘要不属于同一运行");
    }
    if (!Number.isInteger(summary.frame_count) || summary.frame_count <= 0) {
      throw new Error("Fast-WAM 视频帧数无效");
    }
    if (typeof summary.fps !== "number" || !Number.isFinite(summary.fps) || summary.fps <= 0) {
      throw new Error("Fast-WAM 视频帧率无效");
    }
    if (!Array.isArray(actions) || actions.length === 0 || summary.action_count !== actions.length) {
      throw new Error("Fast-WAM 动作数量无效");
    }
    let previousTime = -1;
    let policyCalls = 0;
    actions.forEach(function (action, index) {
      const values = action && action.action;
      if (!action || action.schema_version !== "1.0" || action.run_id !== summary.run_id) {
        throw new Error("Fast-WAM 动作来源无效");
      }
      if (!Number.isInteger(action.sequence) || action.sequence !== index) {
        throw new Error("Fast-WAM 动作序号不连续");
      }
      if (!Number.isInteger(action.observed_frame)
          || action.observed_frame < 0
          || action.observed_frame >= summary.frame_count) {
        throw new Error("Fast-WAM 动作绑定了不存在的视频帧");
      }
      if (typeof action.sim_time_s !== "number" || !Number.isFinite(action.sim_time_s)
          || action.sim_time_s < previousTime) {
        throw new Error("Fast-WAM 动作时间无效");
      }
      previousTime = action.sim_time_s;
      if (!Array.isArray(values) || values.length !== 7 || values.some(function (value) {
        return typeof value !== "number" || !Number.isFinite(value) || value < -1 || value > 1;
      })) {
        throw new Error("Fast-WAM 动作必须是七个有限有界值");
      }
      if (typeof action.model_call !== "boolean"
          || typeof action.latency_s !== "number"
          || !Number.isFinite(action.latency_s)
          || action.latency_s < 0) {
        throw new Error("Fast-WAM 动作调用元数据无效");
      }
      if (action.model_call) policyCalls += 1;
    });
    if (summary.policy_call_count !== policyCalls) {
      throw new Error("Fast-WAM 策略调用数与动作证据不一致");
    }
    const terminal = events[events.length - 1];
    const observedSuccess = terminal.event_type === "task_completed"
      && terminal.status === "COMPLETED"
      && terminal.state
      && terminal.state.official_success === true;
    if (summary.official_success !== observedSuccess
        || (observedSuccess && summary.terminal_status !== "COMPLETED")) {
      throw new Error("Fast-WAM 官方成功谓词与摘要不一致");
    }
    if (!Array.isArray(summary.attempts) || summary.attempts.length !== 5) {
      throw new Error("Fast-WAM 必须保留五次固定初态结果");
    }
    const successes = [];
    summary.attempts.forEach(function (attempt, index) {
      if (!attempt || attempt.attempt_index !== index || typeof attempt.success !== "boolean") {
        throw new Error("Fast-WAM 尝试结果无效");
      }
      if (attempt.success) successes.push(index);
    });
    const selected = successes.length ? successes[0] : null;
    if (summary.selected_attempt !== selected) {
      throw new Error("Fast-WAM 选中尝试不是首次成功尝试");
    }
    return Object.freeze({
      runId: summary.run_id,
      frameCount: summary.frame_count,
      officialSuccess: observedSuccess,
      selectedAttempt: selected
    });
  }

  function fastWamAtFrame(events, actions, frame) {
    if (!Number.isInteger(frame) || frame < 0) throw new Error("Fast-WAM 帧号无效");
    let latestEvent = null;
    let latestAction = null;
    events.forEach(function (event) {
      const observed = event.evidence && event.evidence.observed_frame;
      if (Number.isInteger(observed) && observed <= frame) latestEvent = event;
    });
    actions.forEach(function (action) {
      if (action.observed_frame <= frame) latestAction = action;
    });
    return Object.freeze({event: latestEvent, action: latestAction, frame: frame});
  }

  function fastWamFrame(currentTime, fps, frameCount) {
    if (typeof currentTime !== "number" || !Number.isFinite(currentTime) || currentTime < 0
        || typeof fps !== "number" || !Number.isFinite(fps) || fps <= 0
        || !Number.isInteger(frameCount) || frameCount <= 0) {
      throw new Error("Fast-WAM 播放时钟无效");
    }
    return Math.min(frameCount - 1, Math.floor(currentTime * fps));
  }

  global.SeerProtocol = Object.freeze({
    chooseDefaultRun: chooseDefaultRun,
    dispatchPlan: dispatchPlan,
    eventDisplayTime: eventDisplayTime,
    eventAtTime: eventAtTime,
    fastWamAtFrame: fastWamAtFrame,
    fastWamFrame: fastWamFrame,
    nextConsoleState: nextConsoleState,
    projectEventTimes: projectEventTimes,
    reconcileTask: reconcileTask,
    scrollOptions: scrollOptions,
    validateFastWamEvidence: validateFastWamEvidence,
    validateEvents: validateEvents,
    reduceEvents: reduceEvents
  });
})(this);
