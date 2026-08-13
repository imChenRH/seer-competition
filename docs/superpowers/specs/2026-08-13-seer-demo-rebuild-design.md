# SEER–HVLA Demo 局部重构设计

## 1. 结论

采用“局部重构”：保留 Aily/飞书的任务与技能模型、13 项技能和 10 项 Fallback 定义、Fast-WAM 独立验证、AutoDL 上的 Isaac Sim 6.0.1 环境及已下载资产；重建执行内核、Isaac 场景与录制、飞书桥接、网页面板和证据链。

不选择“保留优化”，因为当前核心缺陷不是局部瑕疵：远端 `execute_task.py` 直接修改 Xform，未执行 `forklift_controller.py`；桥接真实模式在九技能循环中九次启动完整任务；现有场景采用 Y 轴作为高度，而 Isaac Sim 使用 Z-up；控制面板全部由 `setTimeout` 和硬编码成功率驱动。继续小修无法建立可信闭环。

不选择“推倒重来”，因为业务对象、技能/Fallback 编号、飞书表格、远程运行环境、Fast-WAM 模型和资产下载结果均可复用。

## 2. 演示目标与诚实边界

演示证明以下四件事：

1. Aily/飞书能够把卸货指令编排为固定、可审计的九技能任务。
2. 单个任务只触发一次执行；执行器按事件契约逐技能反馈。
3. Isaac Sim 中能看见叉车进入、对位、叉取、起升、退出、对接和放置，并能演示自动恢复与安全停止。
4. Fast-WAM 能独立加载并完成一次推理，但不宣称它正在控制叉车。

本 Demo 明确标注为“规则控制的数字孪生原型”。叉车底盘与货叉采用可重复的运动学轨迹，托盘抓取采用显式载荷耦合；不宣称已经完成真实车辆动力学标定、ROS 2 硬件闭环、SRC-5000 实机控制、真实感知或端到端 VLA 控制。论文的 190 ms 是论文指标；本机测得的 0.86 s 单次结果单独展示。

## 3. 目标架构

```text
Aily / 飞书任务表
        │ 同主机排他锁内乐观认领并回读确认
        ▼
Feishu Bridge ──────── 一次启动 ───────► Demo Engine
        ▲                                   │
        │ 逐事件幂等回写                    ├── dry-run backend（Mac 验证）
        │                                   └── Isaac backend（AutoDL 展示）
        │                                             │
        └────────── JSONL 事件流 ◄────────────────────┘
                              │
                              ├── 证据校验器
                              └── Web 控制台 + 对应视频

Fast-WAM verification ── 独立日志/指标，不进入叉车执行链
```

所有运行都输出只追加 JSONL。网页只读取 JSONL，不自行生成成功事件、Fallback 或指标。视频与 JSONL 使用同一 `run_id` 和场景名绑定。

## 4. 三个演示场景

### normal

严格执行：`FORK-NAV-01 → FORK-NAV-03 → FORK-PER-01 → FORK-OP-01 → FORK-OP-02 → FORK-OP-03 → FORK-NAV-02 → FORK-OP-05 → FORK-OP-04`。最终状态 `COMPLETED`，无 Fallback。

### recovery

在 `FORK-PER-01` 首次校验时产生栈板横向偏移，触发 `FB-F01`；执行重新识别、重新对位和再校验，第二次成功，然后继续九技能并完成。事件和画面都必须出现实际横向重对位。

### intervention

在 `FORK-PER-01` 检测到遮挡，触发 `FB-F02`，三次不同观察位姿仍失败；随后触发 `FB-F07`，车辆退到安全位置并停止，最终状态 `HUMAN_REQUIRED`。不伪造自动恢复或任务完成。

## 5. 事件契约

每行包含：`schema_version`、`run_id`、`sequence`、`scenario`、`event_type`、`source`、`sim_time_s`、`skill_id`、`fallback_id`、`status`、`message`、`state`、`evidence`。

约束：

- `sequence` 从 0 连续递增；`sim_time_s` 单调不减。
- `source` 只能是 `dry_run`、`isaac_sim`、`feishu_bridge` 或 `fastwam_verification`。
- 只有 `skill_completed` 才能推进当前技能。
- 任务终态只能出现一次；`normal/recovery` 为 `COMPLETED`，`intervention` 为 `HUMAN_REQUIRED`。
- `isaac_sim` 的完成事件必须携带可核验状态，例如底盘位置、门架高度、载荷状态。
- UI 不接受缺号、重复、跨 `run_id` 或终态后新增的事件。

## 6. 组件边界

- `contracts.py`：事件结构、序列写入与校验，不依赖飞书或 Isaac。
- `scenarios.py`：技能序列、Fallback 和轨迹关键帧，是三场景唯一事实源。
- `engine.py`：场景状态机；后端只能执行动作和返回观测，不能自行宣布任务成功。
- `backends/dry_run.py`：Mac 上的确定性验证后端，明确标记为 dry-run。
- `bridge.py`：认领一个任务、一次启动 runner、逐事件幂等回写、异常时写失败；不在技能循环中重复启动进程。
- `isaac/scene.py`：Z-up 场景构建，所有子部件使用局部坐标。
- `isaac/runner.py`：按状态机动作驱动场景、同步输出事件和帧；不使用论文模型伪装控制。
- `server.py` 与 `web/`：静态服务、事件/媒体 API 和只读控制台。

## 7. 交付与验收

1. Mac 上一条命令能运行三场景 dry-run、校验证据并打开控制台。
2. AutoDL 上一条命令能运行指定 Isaac 场景并生成 JSONL、MP4 和摘要。
3. 三个 JSONL 均通过连续序列、合法状态迁移和终态校验。
4. 正常视频清楚出现完整叉取与放置；恢复视频出现真实横向重对位；人工介入视频出现遮挡、三次尝试、后退和停车。
5. 飞书桥接测试证明一个九技能任务只启动一次执行器；重复轮询不会重复执行已认领任务。
6. 网页面板显示的数据逐字段来自 JSONL；没有固定 100% 成功率、190 ms 本机指标或“实机控制”文案。
7. 仓库不包含凭证；`.env.example` 只含字段名。
8. README 明确区分：已验证、演示级实现、论文/目标指标、未实现。
