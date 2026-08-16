(function () {
  "use strict";

  const video = document.getElementById("simulation-video");
  const noVideo = document.getElementById("no-video");
  const evidenceContent = document.getElementById("evidence-content");
  const agentConsole = document.getElementById("agent-console");
  const dispatchDetails = document.getElementById("dispatch-details");
  const demoBoundary = document.getElementById("demo-boundary");
  const tabs = Array.from(document.querySelectorAll("[data-scenario]"));
  const taskPresets = {
    normal: "卸载3号集装箱货物到A区传送带",
    recovery: "卸载3号集装箱货物到A区传送带",
    intervention: "处理被倒塌货物遮挡的3号栈板",
    fastwam: "把黑色碗放入盘子"
  };
  const skillNames = {
    "FORK-NAV-01": "进箱导航",
    "FORK-NAV-03": "精确对位",
    "FORK-PER-01": "栈板识别与位姿估计",
    "FORK-OP-01": "货叉插入",
    "FORK-OP-02": "门架起升",
    "FORK-OP-03": "货叉倾斜调整",
    "FORK-NAV-02": "月台区导航",
    "FORK-OP-05": "传送带对接",
    "FORK-OP-04": "栈板放置",
    "ARM-PER-01": "双相机观测",
    "ARM-PLAN-01": "任务语义映射",
    "WAM-ACT-01": "Fast-WAM 动作生成",
    "ARM-OP-01": "接近黑色碗",
    "ARM-OP-02": "夹持黑色碗",
    "ARM-OP-03": "举升与转移",
    "ARM-OP-04": "放入盘子",
    "ARM-VER-01": "官方成功验证"
  };
  let runs = [];
  let activeEvents = [];
  let activeRunId = null;
  let activeFastWam = null;
  let renderGeneration = 0;
  let consoleState = SeerProtocol.nextConsoleState(null, {type: "initialize", scenario: "normal"});

  function setText(id, value) {
    document.getElementById(id).textContent = String(value);
  }

  function renderEvaluationRubric() {
    const target = document.getElementById("evaluation-rubric");
    target.replaceChildren();
    SeerProtocol.evaluationRubric().forEach(function (rubric) {
      const item = document.createElement("li");
      item.className = "evaluation-card";
      item.dataset.rubric = rubric.id;

      const heading = document.createElement("div");
      heading.className = "rubric-heading";
      const weight = document.createElement("strong");
      weight.className = "rubric-weight";
      weight.textContent = rubric.weight + "%";
      const label = document.createElement("span");
      label.className = "rubric-label";
      label.textContent = rubric.label;
      heading.append(weight, label);

      const claim = document.createElement("p");
      claim.className = "rubric-claim";
      claim.textContent = rubric.claim;
      const evidence = document.createElement("p");
      evidence.className = "rubric-evidence";
      evidence.textContent = rubric.evidence;
      item.append(heading, claim, evidence);
      target.append(item);
    });
  }

  async function fetchJson(path) {
    const response = await fetch(path, {cache: "no-store"});
    if (!response.ok) throw new Error(path + " returned " + response.status);
    return response.json();
  }

  async function loadEvents(runId) {
    const response = await fetch("/api/runs/" + encodeURIComponent(runId) + "/events", {cache: "no-store"});
    if (!response.ok) throw new Error("events returned " + response.status);
    const text = await response.text();
    return text.split(/\r?\n/).filter(Boolean).map(function (line) { return JSON.parse(line); });
  }

  async function loadActions(runId) {
    const response = await fetch("/api/runs/" + encodeURIComponent(runId) + "/actions", {cache: "no-store"});
    if (!response.ok) throw new Error("actions returned " + response.status);
    const text = await response.text();
    return text.split(/\r?\n/).filter(Boolean).map(function (line) { return JSON.parse(line); });
  }

  function setActiveTab(scenario) {
    tabs.forEach(function (tab) {
      const active = tab.dataset.scenario === scenario;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
  }

  function collapseDetails() {
    setConsoleCompact(false);
    renderGeneration += 1;
    activeRunId = null;
    activeEvents = [];
    activeFastWam = null;
    evidenceContent.hidden = true;
    dispatchDetails.hidden = true;
    demoBoundary.hidden = true;
    video.pause();
    video.currentTime = 0;
    setText("active-instruction", "未开始");
    setText("active-behavior", "等待小脑层");
    setText("active-audit", "#—");
    document.getElementById("dispatch-plan").replaceChildren();
  }

  function selectScenario(scenario) {
    consoleState = SeerProtocol.nextConsoleState(consoleState, {type: "select", scenario: scenario});
    collapseDetails();
    setActiveTab(scenario);
    document.getElementById("task-input").value = taskPresets[scenario];
    setText("chat-response", "已选择“" + taskPresets[scenario] + "”。点击发送后才会载入对应视频与审计证据。");
  }

  function renderSkills(events) {
    const list = document.getElementById("skill-list");
    list.replaceChildren();
    events.filter(function (event) { return event.event_type === "skill_completed"; }).forEach(function (event, index) {
      const item = document.createElement("li");
      const number = document.createElement("span");
      number.className = "skill-index";
      number.textContent = String(index + 1).padStart(2, "0");
      const name = document.createElement("div");
      const label = document.createElement("div");
      label.className = "skill-label";
      label.textContent = skillNames[event.skill_id] || "未知技能";
      const id = document.createElement("div");
      id.className = "skill-code";
      id.textContent = event.skill_id;
      name.append(label, id);
      const time = document.createElement("span");
      time.className = "skill-time";
      time.textContent = SeerProtocol.eventDisplayTime(event).toFixed(1) + "s";
      item.append(number, name, time);
      list.append(item);
    });
  }

  function renderFallbacks(events) {
    const target = document.getElementById("fallback-list");
    target.replaceChildren();
    const relevant = events.filter(function (event) {
      return ["fallback_started", "fallback_completed", "safety_stop", "human_intervention_requested"].includes(event.event_type);
    });
    if (relevant.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.style.minHeight = "120px";
      empty.textContent = "本次运行没有触发 Fallback 或安全事件。";
      target.append(empty);
      return;
    }
    relevant.forEach(function (event) {
      const card = document.createElement("div");
      card.className = "event-card" + (event.event_type.includes("safety") || event.event_type.includes("human") ? " safety" : "");
      const title = document.createElement("strong");
      title.textContent = (event.fallback_id || event.event_type) + " · " + event.event_type;
      const detail = document.createElement("span");
      detail.textContent = event.message || "—";
      card.append(title, detail);
      target.append(card);
    });
  }

  function renderLog(events) {
    const log = document.getElementById("event-log");
    log.replaceChildren();
    events.forEach(function (event) {
      const row = document.createElement("div");
      row.className = "log-row";
      const seq = document.createElement("span");
      seq.className = "log-seq";
      seq.textContent = "#" + event.sequence;
      const type = document.createElement("span");
      type.className = "log-type";
      type.textContent = event.event_type;
      const message = document.createElement("span");
      message.textContent = event.message || event.skill_id || "—";
      row.append(seq, type, message);
      log.append(row);
    });
  }

  function renderDispatchPlan(events) {
    const target = document.getElementById("dispatch-plan");
    target.replaceChildren();
    SeerProtocol.dispatchPlan(events).forEach(function (step) {
      const item = document.createElement("li");
      item.dataset.sequence = String(step.sequence);
      item.dataset.time = String(step.simTimeS);
      item.textContent = step.identifier + " · " + step.layer;
      target.append(item);
    });
  }

  function updatePlaybackState(simTimeS) {
    const event = SeerProtocol.eventAtTime(activeEvents, simTimeS);
    if (!event) return;
    const identifier = event.fallback_id || event.skill_id;
    setText("active-instruction", event.message || event.event_type);
    setText("active-behavior", identifier ? (identifier + " · " + (skillNames[identifier] || event.event_type)) : event.event_type);
    setText("active-audit", "#" + event.sequence + " · " + event.status);
    document.querySelectorAll("#dispatch-plan li").forEach(function (item) {
      const start = Number(item.dataset.time);
      item.classList.toggle("active", start <= simTimeS && identifier && item.textContent.startsWith(identifier));
    });
  }

  function scrollEvidenceIntoView(target) {
    const reducedMotion = typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView(SeerProtocol.scrollOptions(reducedMotion));
  }

  function setConsoleCompact(compact) {
    agentConsole.classList.toggle("compact", Boolean(compact));
  }

  function playbackSegments(events) {
    const starts = new Map();
    const segments = [];
    events.forEach(function (event) {
      const time = SeerProtocol.eventDisplayTime(event);
      if (typeof time !== "number") return;
      const attempt = event.evidence && Number.isInteger(event.evidence.attempt)
        ? event.evidence.attempt : 1;
      if (event.event_type === "skill_started" && event.skill_id) {
        starts.set("s:" + event.skill_id + ":" + attempt, {time: time, id: event.skill_id, kind: "skill"});
      } else if (event.event_type === "fallback_started" && event.fallback_id) {
        starts.set("f:" + event.fallback_id + ":" + attempt, {time: time, id: event.fallback_id, kind: "fallback"});
      } else if (event.event_type === "skill_completed" && event.skill_id) {
        const key = "s:" + event.skill_id + ":" + attempt;
        const start = starts.get(key);
        if (start && time >= start.time) {
          segments.push({kind: "skill", label: skillNames[event.skill_id] || event.skill_id, start: start.time, end: time});
        }
      } else if (event.event_type === "fallback_completed" && event.fallback_id) {
        const key = "f:" + event.fallback_id + ":" + attempt;
        const start = starts.get(key);
        if (start && time >= start.time) {
          segments.push({kind: "fallback", label: event.fallback_id, start: start.time, end: time});
        }
      } else if (event.event_type === "safety_stop" || event.event_type === "human_intervention_requested") {
        segments.push({kind: "safety", label: event.event_type === "safety_stop" ? "安全停车" : "人工接管", start: time, end: time + 0.1});
      }
    });
    return segments.filter(function (segment) { return segment.end >= segment.start; });
  }

  function renderPlaybackTrack(events, targetId, mediaElement, displaySegments) {
    const target = document.getElementById(targetId);
    if (!target) return;
    target.replaceChildren();
    const segments = displaySegments || playbackSegments(events);
    const total = segments.reduce(function (max, segment) { return Math.max(max, segment.end); }, 0.001);
    segments.forEach(function (segment) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "track-segment " + (segment.kind === "skill" ? "" : segment.kind);
      button.textContent = segment.label;
      button.title = segment.label + " · " + segment.start.toFixed(1) + "s – " + segment.end.toFixed(1) + "s";
      button.dataset.start = String(segment.start);
      button.style.flexGrow = String(SeerProtocol.timelineFlexWeight(segment.start, segment.end));
      button.addEventListener("click", function () {
        const duration = mediaElement.duration || segment.end;
        mediaElement.currentTime = Math.min(segment.start + 0.02, Math.max(0, duration - 0.02));
        mediaElement.play().catch(function () {});
      });
      target.append(button);
    });
    updateTrackActive(mediaElement.currentTime, targetId);
  }

  function updateTrackActive(currentTime, targetId) {
    const target = document.getElementById(targetId);
    if (!target) return;
    target.querySelectorAll(".track-segment").forEach(function (button) {
      const start = Number(button.dataset.start);
      const next = button.nextElementSibling ? Number(button.nextElementSibling.dataset.start) : Infinity;
      button.classList.toggle("active", currentTime >= start && currentTime < next);
    });
  }

  async function renderRun(runId, expectedScenario) {
    const generation = ++renderGeneration;
    const pair = await Promise.all([fetchJson("/api/runs/" + encodeURIComponent(runId)), loadEvents(runId)]);
    if (generation !== renderGeneration) return;
    if (consoleState.selectedScenario !== expectedScenario) return;
    const summary = pair[0];
    const events = pair[1];
    const projectedEvents = SeerProtocol.projectEventTimes(events, Number(summary.fps));
    const reduced = SeerProtocol.reduceEvents(projectedEvents);
    activeRunId = runId;
    activeEvents = projectedEvents;
    activeFastWam = null;
    video.defaultPlaybackRate = 1;
    video.playbackRate = 1;
    evidenceContent.hidden = false;
    dispatchDetails.hidden = false;
    demoBoundary.hidden = false;
    setConsoleCompact(true);
    setText("metric-status", reduced.terminalStatus);
    setText("metric-skills", reduced.completedSkills.length + " / 9");
    setText("metric-fallbacks", reduced.fallbackCount);
    setText("metric-duration", reduced.durationS.toFixed(1) + " s");
    setText("metric-duration-label", "证据时长");
    setText("timeline-hint", "点击阶段可跳转");
    setText("source-pill", reduced.source);
    setText("event-count", reduced.eventCount + " events");
    setText("run-meta", reduced.runId + " · " + reduced.scenario + " · " + (summary.controller || "evidence replay"));
    setText("video-eyebrow", "ISAAC SIM × ARCHITECTURE VIEW");
    setText("video-heading", "仿真与双层架构同步画面");
    setText("skills-heading", "技能执行链");
    setText("lower-left-eyebrow", "FALLBACK & SAFETY");
    setText("lower-left-heading", "恢复与安全事件");
    noVideo.textContent = "该运行是 Mac dry-run，仅有逻辑证据，没有仿真视频。";
    renderSkills(projectedEvents);
    renderFallbacks(projectedEvents);
    renderLog(projectedEvents);
    renderDispatchPlan(projectedEvents);
    renderPlaybackTrack(projectedEvents, "phase-track", video);
    updatePlaybackState(0);
    const preferredMedia = summary.has_presentation ? summary.presentation_file : (summary.has_video ? summary.video_file : null);
    if (preferredMedia) {
      noVideo.hidden = true;
      video.hidden = false;
      video.src = "/media/" + encodeURIComponent(runId) + "/" + encodeURIComponent(preferredMedia);
    } else {
      video.removeAttribute("src");
      video.load();
      video.hidden = true;
      noVideo.hidden = false;
    }
    return projectedEvents;
  }

  function runForScenario(scenario) {
    return runs.find(function (run) {
      return run.scenario === scenario && run.source === "isaac_sim";
    }) || runs.find(function (run) { return run.scenario === scenario; });
  }

  function renderFastWamDetails(summary, event, action) {
    const target = document.getElementById("fallback-list");
    target.replaceChildren();
    const state = event && event.state ? event.state : {};
    const officialSuccess = Boolean(
      event && state.official_success === true
      && (event.event_type === "skill_completed" || event.event_type === "task_completed")
    );

    function addCard(titleText, detailText, safety) {
      const card = document.createElement("div");
      card.className = "event-card" + (safety ? " safety" : "");
      const title = document.createElement("strong");
      title.textContent = titleText;
      const detail = document.createElement("span");
      detail.textContent = detailText;
      card.append(title, detail);
      target.append(card);
    }

    const bowlLift = typeof state.bowl_lift_m === "number"
      ? state.bowl_lift_m.toFixed(3) + " m" : "—";
    const targetError = typeof state.plate_xy_error_m === "number"
      ? state.plate_xy_error_m.toFixed(3) + " m" : "—";
    addCard(
      "官方任务与物理观测",
      "env.check_success=" + (officialSuccess ? "TRUE" : "FALSE")
        + " · 碗举升=" + bowlLift
        + " · 目标误差=" + targetError
        + " · 夹爪=" + (state.gripper_closed ? "闭合" : "打开/过渡"),
      false
    );
    addCard(
      "Fast-WAM 当前 7-D 相对动作",
      action ? action.action.map(function (value) { return Number(value).toFixed(3); }).join(" · ")
        + " · " + (action.model_call ? "新策略调用" : "动作队列")
        + " · " + action.latency_s.toFixed(3) + " s" : "尚无已执行动作",
      false
    );
    summary.attempts.forEach(function (attempt) {
      addCard(
        "INIT " + attempt.attempt_index + " · " + (attempt.success ? "成功" : "未成功"),
        String(attempt.executed_steps === undefined ? "—" : attempt.executed_steps)
          + " steps · " + (attempt.terminal_reason || "—"),
        !attempt.success
      );
    });
    addCard("证据边界", summary.claim_boundary || "仅证明五个固定初态的官方任务运行结果。", false);
  }

  async function fetchFastWamEvidence(expectedScenario, generation) {
    const envelope = await fetchJson("/api/fastwam");
    if (generation !== renderGeneration) return;
    if (consoleState.selectedScenario !== expectedScenario) return null;
    if (!envelope.rollout) throw new Error("没有通过完整校验的 Fast-WAM 闭环运行");
    const runId = envelope.rollout.run_id;
    const batch = await Promise.all([
      fetchJson("/api/runs/" + encodeURIComponent(runId)),
      loadEvents(runId),
      loadActions(runId)
    ]);
    if (generation !== renderGeneration) return;
    if (consoleState.selectedScenario !== expectedScenario) return null;
    const summary = batch[0];
    const events = batch[1];
    const actions = batch[2];
    SeerProtocol.validateFastWamEvidence(summary, events, actions);
    if (generation !== renderGeneration) return;
    if (consoleState.selectedScenario !== expectedScenario) return null;
    return Object.freeze({
      envelope: envelope,
      summary: summary,
      events: events,
      actions: actions
    });
  }

  function syncFastWamPlayback(currentTime) {
    if (!activeFastWam) return;
    const summary = activeFastWam.summary;
    const frame = SeerProtocol.fastWamFrame(
      currentTime,
      Number(summary.presentation_fps || summary.fps),
      summary.frame_count
    );
    const projected = SeerProtocol.fastWamAtFrame(activeFastWam.events, activeFastWam.actions, frame);
    const event = projected.event;
    const action = projected.action;
    if (!event) return;
    const phase = event.skill_id || event.event_type;
    renderFastWamDetails(summary, event, action);
    setText("active-instruction", event.message || phase);
    setText("active-behavior", phase + " · " + (skillNames[phase] || event.event_type));
    setText("active-audit", "#" + event.sequence + " · frame " + frame);
  }

  async function showFastWam(expectedScenario, taskDecision) {
    const generation = ++renderGeneration;
    activeRunId = null;
    activeEvents = [];
    video.pause();
    const evidence = await fetchFastWamEvidence(expectedScenario, generation);
    if (!evidence) return;
    const summary = evidence.summary;
    activeRunId = summary.run_id;
    activeEvents = SeerProtocol.projectEventTimes(evidence.events, Number(summary.fps));
    activeFastWam = evidence;
    evidenceContent.hidden = false;
    dispatchDetails.hidden = false;
    demoBoundary.hidden = false;
    setConsoleCompact(true);
    const reduced = SeerProtocol.reduceEvents(activeEvents);
    const presentationFps = Number(summary.presentation_fps || summary.fps);
    const playbackPlan = SeerProtocol.fastWamPlaybackPlan(
      playbackSegments(activeEvents),
      reduced.durationS,
      Number(summary.fps),
      presentationFps
    );
    setText("metric-status", reduced.terminalStatus);
    setText("metric-skills", reduced.completedSkills.length + " / 8");
    setText("metric-fallbacks", "0");
    setText("metric-duration", playbackPlan.presentationDurationS.toFixed(1) + " s");
    setText(
      "metric-duration-label",
      playbackPlan.playbackRate < 1 ? "展示时长（0.5× 慢放）" : "展示时长（视频已延长）"
    );
    setText(
      "timeline-hint",
      playbackPlan.playbackRate < 1
        ? "前 3 个准备阶段已隐藏 · 0.5× 慢速播放"
        : "前 3 个准备阶段已隐藏 · 视频已延长至 2×"
    );
    setText("source-pill", "fastwam_policy");
    setText("event-count", reduced.eventCount + " events");
    setText("run-meta", summary.run_id + " · fastwam_bowl_plate · official LIBERO task 8");
    setText("video-eyebrow", "LIBERO / MUJOCO × ARCHITECTURE VIEW");
    setText("video-heading", "仿真与双层架构同步画面");
    setText("skills-heading", "技能执行链");
    setText("lower-left-eyebrow", "POLICY & OFFICIAL PREDICATE");
    setText("lower-left-heading", "Fast-WAM 动作与五次初态证据");
    renderSkills(activeEvents);
    renderLog(activeEvents);
    renderDispatchPlan(activeEvents);
    renderPlaybackTrack(activeEvents, "phase-track", video, playbackPlan.segments);
    video.defaultPlaybackRate = playbackPlan.playbackRate;
    video.playbackRate = playbackPlan.playbackRate;
    const media = summary.has_presentation ? summary.presentation_file : (summary.has_video ? summary.video_file : null);
    if (media) {
      noVideo.hidden = true;
      video.hidden = false;
      video.src = "/media/" + encodeURIComponent(summary.run_id) + "/" + encodeURIComponent(media);
    } else {
      video.removeAttribute("src");
      video.load();
      video.hidden = true;
      noVideo.hidden = false;
      noVideo.textContent = "当前没有通过完整证据校验的 Fast-WAM 录像。";
    }
    video.currentTime = 0;
    syncFastWamPlayback(0);
    setText(
      "chat-response",
      taskDecision.accepted
        ? "任务已映射到官方 LIBERO task 8；下方重放 Fast-WAM 的 7-D 策略动作、五次固定初态结果与官方成功谓词。"
        : "输入与证据不一致，未伪造 Fast-WAM 执行；已切换为可审计任务：" + taskDecision.task
    );
    if (!video.hidden) video.play().catch(function () { /* browser may require another gesture */ });
  }

  async function dispatchCurrentEvidence() {
    const scenario = consoleState.selectedScenario;
    consoleState = SeerProtocol.nextConsoleState(consoleState, {type: "dispatch"});
    setText("chat-response", "任务已发送，正在读取本地可验证证据…");
    if (scenario === "fastwam") {
      const fastwamInput = document.getElementById("task-input");
      const fastwamDecision = SeerProtocol.reconcileTask(fastwamInput.value, taskPresets.fastwam);
      fastwamInput.value = fastwamDecision.task;
      await showFastWam(scenario, fastwamDecision);
      scrollEvidenceIntoView(evidenceContent);
      return;
    }
    const run = runForScenario(scenario);
    if (!run) throw new Error("所选模式没有可验证运行");
    const requested = document.getElementById("task-input").value.trim();
    const events = await renderRun(run.run_id, scenario);
    if (!events || consoleState.selectedScenario !== scenario) return;
    const task = events.find(function (event) { return event.event_type === "task_started"; });
    const recorded = task && task.message ? task.message : "当前已验证任务";
    const input = document.getElementById("task-input");
    const taskDecision = SeerProtocol.reconcileTask(requested, recorded);
    if (!taskDecision.accepted) {
      setText("chat-response", "输入与证据不一致，未伪造执行；已切换为可审计任务：" + recorded);
      input.value = taskDecision.task;
    } else {
      setText("chat-response", "意图已结构化并分发 " + SeerProtocol.dispatchPlan(activeEvents).length + " 个技能/Fallback 节点；开始重放已验证证据。");
    }
    video.currentTime = 0;
    updatePlaybackState(0);
    scrollEvidenceIntoView(evidenceContent);
    if (!video.hidden) video.play().catch(function () { /* browser may require another gesture */ });
  }

  async function populateRunBadges(runList) {
    const badgeCache = new Map();
    async function statsFor(run) {
      if (badgeCache.has(run.run_id)) return badgeCache.get(run.run_id);
      const events = await loadEvents(run.run_id);
      const fps = Number(run.fps || 0);
      const projected = fps > 0 ? SeerProtocol.projectEventTimes(events, fps) : events;
      const reduced = SeerProtocol.reduceEvents(projected);
      const result = {
        skills: reduced.completedSkills.length,
        fallbacks: reduced.fallbackCount,
        terminal: reduced.terminalStatus
      };
      badgeCache.set(run.run_id, result);
      return result;
    }
    for (const run of runList) {
      const badgeScenario = run.scenario === "fastwam_bowl_plate" ? "fastwam" : run.scenario;
      const badge = document.querySelector('[data-badge-for="' + badgeScenario + '"]');
      try {
        const stats = await statsFor(run);
        if (!badge) continue;
        if (run.source === "fastwam_policy") {
          badge.textContent = (typeof run.success_count === "number" ? run.success_count : "—") + "/5 · 官方成功";
          setText("hero-stat-fastwam", "Fast-WAM " + (run.success_count || 0) + "/5 官方成功");
        } else {
          const fallbackText = stats.fallbacks > 0 ? " · " + stats.fallbacks + " Fallback" : "";
          badge.textContent = stats.skills + "/9 · " + stats.terminal + fallbackText;
        }
      } catch (_) {
        if (badge) badge.textContent = "证据读取失败";
      }
    }
  }

  function toggleDemoMode() {
    const enabled = document.body.classList.toggle("demo-mode");
    const button = document.getElementById("demo-mode-toggle");
    button.setAttribute("aria-pressed", String(enabled));
    button.textContent = enabled ? "退出演示模式" : "演示模式";
  }

  async function quickStart(scenario) {
    selectScenario(scenario);
    await dispatchCurrentEvidence();
  }

  async function initialize() {
    renderEvaluationRubric();
    try {
      const payload = await fetchJson("/api/runs");
      runs = payload.runs;
      SeerProtocol.chooseDefaultRun(runs);
      populateRunBadges(runs);
      selectScenario("normal");
    } catch (error) {
      showError(error);
    }
  }

  function showError(error) {
    setText("run-meta", "证据加载失败：" + error.message);
    setText("chat-response", "加载失败，未执行任何动作。" + error.message);
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      selectScenario(tab.dataset.scenario);
    });
  });
  document.getElementById("dispatch-button").addEventListener("click", function () {
    dispatchCurrentEvidence().catch(showError);
  });
  document.getElementById("quick-normal").addEventListener("click", function () {
    quickStart("normal").catch(showError);
  });
  document.getElementById("quick-fastwam").addEventListener("click", function () {
    quickStart("fastwam").catch(showError);
  });
  document.getElementById("demo-mode-toggle").addEventListener("click", toggleDemoMode);
  video.addEventListener("timeupdate", function () {
    if (activeFastWam) syncFastWamPlayback(video.currentTime);
    else updatePlaybackState(video.currentTime);
    updateTrackActive(video.currentTime, "phase-track");
  });
  video.addEventListener("ended", function () {
    if (activeFastWam) syncFastWamPlayback(video.duration || 0);
    else updatePlaybackState(video.duration || 0);
    updateTrackActive(video.duration || 0, "phase-track");
  });
  initialize();
})();
