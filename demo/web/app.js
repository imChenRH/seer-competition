(function () {
  "use strict";

  const video = document.getElementById("simulation-video");
  const noVideo = document.getElementById("no-video");
  const evidenceContent = document.getElementById("evidence-content");
  const fastwamContent = document.getElementById("fastwam-content");
  const dispatchDetails = document.getElementById("dispatch-details");
  const demoBoundary = document.getElementById("demo-boundary");
  const tabs = Array.from(document.querySelectorAll("[data-scenario]"));
  const taskPresets = {
    normal: "卸载3号集装箱货物到A区传送带",
    recovery: "卸载3号集装箱货物到A区传送带",
    intervention: "处理被倒塌货物遮挡的3号栈板",
    fastwam: "验证 Fast-WAM 本地模型加载与单批推理"
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
    "FORK-OP-04": "栈板放置"
  };
  let runs = [];
  let activeEvents = [];
  let activeRunId = null;
  let renderGeneration = 0;
  let consoleState = SeerProtocol.nextConsoleState(null, {type: "initialize", scenario: "normal"});

  function setText(id, value) {
    document.getElementById(id).textContent = String(value);
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

  function setActiveTab(scenario) {
    tabs.forEach(function (tab) {
      const active = tab.dataset.scenario === scenario;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
  }

  function collapseDetails() {
    renderGeneration += 1;
    activeRunId = null;
    activeEvents = [];
    evidenceContent.hidden = true;
    fastwamContent.hidden = true;
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
      const id = document.createElement("div");
      id.className = "skill-id";
      id.textContent = event.skill_id;
      const label = document.createElement("div");
      label.textContent = skillNames[event.skill_id] || "未知技能";
      label.style.fontSize = "12px";
      label.style.color = "#61717d";
      name.append(id, label);
      const time = document.createElement("span");
      time.className = "skill-time";
      time.textContent = event.sim_time_s.toFixed(1) + "s";
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

  async function renderRun(runId, expectedScenario) {
    const generation = ++renderGeneration;
    const pair = await Promise.all([fetchJson("/api/runs/" + encodeURIComponent(runId)), loadEvents(runId)]);
    if (generation !== renderGeneration) return;
    if (consoleState.selectedScenario !== expectedScenario) return;
    const summary = pair[0];
    const events = pair[1];
    const reduced = SeerProtocol.reduceEvents(events);
    activeRunId = runId;
    activeEvents = events;
    evidenceContent.hidden = false;
    fastwamContent.hidden = true;
    dispatchDetails.hidden = false;
    demoBoundary.hidden = false;
    setText("metric-status", reduced.terminalStatus);
    setText("metric-skills", reduced.completedSkills.length + " / 9");
    setText("metric-fallbacks", reduced.fallbackCount);
    setText("metric-duration", reduced.durationS.toFixed(1) + " s");
    setText("source-pill", reduced.source);
    setText("event-count", reduced.eventCount + " events");
    setText("run-meta", reduced.runId + " · " + reduced.scenario + " · " + (summary.controller || "evidence replay"));
    renderSkills(events);
    renderFallbacks(events);
    renderLog(events);
    renderDispatchPlan(events);
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
    return events;
  }

  function runForScenario(scenario) {
    return runs.find(function (run) {
      return run.scenario === scenario && run.source === "isaac_sim";
    }) || runs.find(function (run) { return run.scenario === scenario; });
  }

  async function showFastWam(expectedScenario, taskDecision) {
    const generation = ++renderGeneration;
    activeRunId = null;
    activeEvents = [];
    video.pause();
    const result = await fetchJson("/api/fastwam");
    if (generation !== renderGeneration) return;
    if (consoleState.selectedScenario !== expectedScenario) return;
    evidenceContent.hidden = true;
    fastwamContent.hidden = false;
    dispatchDetails.hidden = true;
    demoBoundary.hidden = false;
    setText("fastwam-status", result.available ? "证据可用" : "无本地证据");
    setText("fastwam-claim", result.claim_boundary);
    setText("fastwam-shape", result.action_shape || "—");
    setText("fastwam-latency", result.single_call_latency_s === null ? "—" : result.single_call_latency_s.toFixed(2) + " s");
    setText(
      "chat-response",
      taskDecision.accepted
        ? "已发送独立验证任务；下方只展示 Fast-WAM 本地模型加载与单批推理证据，不外推为叉车控制能力。"
        : "输入与证据不一致，未伪造 Fast-WAM 执行；已切换为可审计任务：" + taskDecision.task
    );
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
    if (!video.hidden) video.play().catch(function () { /* browser may require another gesture */ });
  }

  async function initialize() {
    try {
      const payload = await fetchJson("/api/runs");
      runs = payload.runs;
      SeerProtocol.chooseDefaultRun(runs);
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
  video.addEventListener("timeupdate", function () { updatePlaybackState(video.currentTime); });
  video.addEventListener("ended", function () { updatePlaybackState(video.duration || 0); });
  initialize();
})();
