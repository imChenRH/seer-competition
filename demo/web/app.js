(function () {
  "use strict";

  const select = document.getElementById("run-select");
  const video = document.getElementById("simulation-video");
  const noVideo = document.getElementById("no-video");
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

  async function renderRun(runId) {
    const pair = await Promise.all([fetchJson("/api/runs/" + encodeURIComponent(runId)), loadEvents(runId)]);
    const summary = pair[0];
    const events = pair[1];
    const reduced = SeerProtocol.reduceEvents(events);
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
    if (summary.has_video) {
      noVideo.hidden = true;
      video.hidden = false;
      video.src = "/media/" + encodeURIComponent(runId) + "/simulation.mp4";
    } else {
      video.removeAttribute("src");
      video.load();
      video.hidden = true;
      noVideo.hidden = false;
    }
  }

  async function initialize() {
    try {
      const payload = await fetchJson("/api/runs");
      select.replaceChildren();
      payload.runs.forEach(function (run) {
        const option = document.createElement("option");
        option.value = run.run_id;
        option.textContent = run.scenario + " · " + run.source + " · " + run.run_id;
        select.append(option);
      });
      const defaultRun = SeerProtocol.chooseDefaultRun(payload.runs);
      select.value = defaultRun.run_id;
      await renderRun(defaultRun.run_id);
      select.addEventListener("change", function () { renderRun(select.value).catch(showError); });
    } catch (error) {
      showError(error);
    }
  }

  function showError(error) {
    setText("run-meta", "证据加载失败：" + error.message);
  }

  initialize();
})();
