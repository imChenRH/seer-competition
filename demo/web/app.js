(function () {
  "use strict";

  const select = document.getElementById("run-select");
  const video = document.getElementById("simulation-video");
  const noVideo = document.getElementById("no-video");
  const evidenceContent = document.getElementById("evidence-content");
  const fastwamContent = document.getElementById("fastwam-content");
  const tabs = Array.from(document.querySelectorAll("[data-scenario]"));
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

  async function renderRun(runId) {
    const generation = ++renderGeneration;
    const pair = await Promise.all([fetchJson("/api/runs/" + encodeURIComponent(runId)), loadEvents(runId)]);
    if (generation !== renderGeneration) return;
    const summary = pair[0];
    const events = pair[1];
    const reduced = SeerProtocol.reduceEvents(events);
    activeRunId = runId;
    activeEvents = events;
    evidenceContent.hidden = false;
    fastwamContent.hidden = true;
    setActiveTab(reduced.scenario);
    select.value = runId;
    setText("metric-status", reduced.terminalStatus);
    setText("metric-skills", reduced.completedSkills.length + " / 9");
    setText("metric-fallbacks", reduced.fallbackCount);
    setText("metric-duration", reduced.durationS.toFixed(1) + " s");
    setText("source-pill", reduced.source);
    setText("event-count", reduced.eventCount + " events");
    setText("run-meta", reduced.runId + " · " + reduced.scenario + " · " + (summary.controller || "evidence replay"));
    const task = events.find(function (event) { return event.event_type === "task_started"; });
    if (task && task.message) document.getElementById("task-input").value = task.message;
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
  }

  function runForScenario(scenario) {
    return runs.find(function (run) {
      return run.scenario === scenario && run.source === "isaac_sim";
    }) || runs.find(function (run) { return run.scenario === scenario; });
  }

  async function showFastWam() {
    const generation = ++renderGeneration;
    activeRunId = null;
    activeEvents = [];
    video.pause();
    setActiveTab("fastwam");
    evidenceContent.hidden = true;
    fastwamContent.hidden = false;
    const result = await fetchJson("/api/fastwam");
    if (generation !== renderGeneration) return;
    setText("fastwam-status", result.available ? "证据可用" : "无本地证据");
    setText("fastwam-claim", result.claim_boundary);
    setText("fastwam-shape", result.action_shape || "—");
    setText("fastwam-latency", result.single_call_latency_s === null ? "—" : result.single_call_latency_s.toFixed(2) + " s");
  }

  function dispatchCurrentEvidence() {
    if (!activeRunId || activeEvents.length === 0) return;
    const task = activeEvents.find(function (event) { return event.event_type === "task_started"; });
    const recorded = task && task.message ? task.message : "当前已验证任务";
    const input = document.getElementById("task-input");
    if (input.value.trim() !== recorded) {
      setText("chat-response", "输入与证据不一致，未伪造执行；已切换为可审计任务：" + recorded);
      input.value = recorded;
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
      select.replaceChildren();
      runs.forEach(function (run) {
        const option = document.createElement("option");
        option.value = run.run_id;
        option.textContent = run.scenario + " · " + run.source + " · " + run.run_id;
        select.append(option);
      });
      const defaultRun = SeerProtocol.chooseDefaultRun(runs);
      await renderRun(defaultRun.run_id);
    } catch (error) {
      showError(error);
    }
  }

  function showError(error) {
    setText("run-meta", "证据加载失败：" + error.message);
    setText("chat-response", "加载失败，未执行任何动作。" + error.message);
  }

  select.addEventListener("change", function () { renderRun(select.value).catch(showError); });
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      const scenario = tab.dataset.scenario;
      if (scenario === "fastwam") {
        showFastWam().catch(showError);
        return;
      }
      const run = runForScenario(scenario);
      if (run) renderRun(run.run_id).catch(showError);
    });
  });
  document.getElementById("dispatch-button").addEventListener("click", dispatchCurrentEvidence);
  video.addEventListener("timeupdate", function () { updatePlaybackState(video.currentTime); });
  video.addEventListener("ended", function () { updatePlaybackState(video.duration || 0); });
  initialize();
})();
