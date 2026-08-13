# Chat-first Web Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将网页改为四种模式加飞书式对话的首屏，并确保只有发送任务后才显示视频和证据。

**Architecture:** 模式按钮只改变 `selectedScenario` 和预填消息；发送动作才通过 `renderRun` 或 `showFastWam` 加载内容。`evidence-content` 与 `fastwam-content` 共用显式收起函数，异步渲染继续受 generation 保护。

**Tech Stack:** 原生 HTML/CSS/JavaScript、JavaScriptCore、Python unittest、本地浏览器。

## Global Constraints

- 只保留四个模式按钮，不存在 `run-select`。
- 初始和每次模式切换后不显示视频/证据详情。
- 任意输入不生成或暗示虚假执行。
- 参考图缺失时不伪造图片来源。

---

### Task 1: DOM contract and state reducer

**Files:**
- Modify: `demo/web/index.html`
- Modify: `demo/web/protocol.js`
- Modify: `tests/test_web_protocol.py`
- Modify: `tests/web_protocol_test.js`

**Interfaces:**
- Produces: `SeerProtocol.nextConsoleState(state, action) -> state`
- DOM: `#preflight-content`, `#evidence-content`, `#fastwam-content`, `#dispatch-button`

- [x] 写失败测试，验证没有 `run-select`，证据区初始 hidden，并验证 reducer 的 select 行为收起内容、dispatch 行为展开所选模式。
- [x] 运行 Python/JSC 聚焦测试，确认旧 DOM 和缺失 reducer 导致失败。
- [x] 实现最小 reducer 和 DOM 结构。
- [x] 重跑聚焦测试直到通过。

### Task 2: Chat-first controller and Feishu styling

**Files:**
- Modify: `demo/web/app.js`
- Modify: `demo/web/styles.css`
- Test: `tests/test_web_protocol.py`
- Test: `tests/web_protocol_test.js`

- [x] 写失败测试，验证初始化不调用证据渲染、模式点击只预选并收起、发送才调用对应渲染。
- [x] 运行测试确认失败来自旧的 initialize/renderRun 流程。
- [x] 删除下拉框控制器；实现 `selectedScenario`、预填任务、收起/展开和发送门控；将对话区改为飞书式应用栏、标题栏、消息流和输入区。
- [x] 运行 JSC、Python 与 JavaScript 语法检查。

### Task 3: Browser acceptance

**Files:**
- Modify: `demo/README.md`
- Modify: `demo/UPGRADE-REPORT-2026-08-13.md`

- [x] 启动本地服务并检查首屏只有四按钮和对话窗，DOM 中视频为隐藏状态。
- [x] 逐一选择四个模式，确认切换后仍隐藏证据且任务预填正确。
- [x] 点击发送，确认前三种模式显示正确视频、Fast-WAM 显示独立验证页。
- [x] 更新使用说明与第二轮修正报告。
