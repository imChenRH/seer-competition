# 物理化与四 Tab 展示补充规格

日期：2026-08-13
来源：用户提供的 `codex-upgrade-prompt.md`
状态：并入双层仓库视频方案，直接实施

## 1. 不变的证据纪律

- `events.jsonl` 仍是任务唯一事实源。
- 不改变事件契约、九技能语义和三场景终态。
- 不把规则控制、运动学目标或 Fast-WAM 论文/独立验证结果描述成叉车真机能力。
- 网页的技能、时长、Fallback、指令字幕和表格更新全部从事件流派生。

## 2. 仿真物理化落地范围

本轮采用任务书明确允许的降级路径：`运动学目标 + 显式物理附着`。

必须实现：

- USD `PhysicsScene`。
- 可交互几何的 `CollisionAPI`。
- 叉车与载荷的 `RigidBodyAPI`、`MassAPI`；两者设为可审计的 kinematic rigid body，避免把直接目标轨迹冒充轮驱动力学。
- 叉车根的 `ArticulationRootAPI` 元数据，保留未来替换真叉车 USD/URDF 的接口边界。
- 托盘由上部货物与下部托盘组成，底部几何留下两个与货叉对应的 fork pockets。
- 抓取使用显式 `FixedJoint` 附着，插叉完成时启用，放置释放时关闭；事件观测同时检查几何关系和 joint 状态。
- 官方 concrete、metal、cardboard、rubber 物理材料 USD 分别绑定到地面、叉车/货架、载荷和车轮。

本轮不声称实现：

- 真实差速轮驱、轮胎接触 PID、液压门架动力学。
- 真实叉车 CAD/URDF 的关节级控制。
- Fast-WAM 控制叉车。

这些内容写入“待企业/人类协助”清单，不阻塞可运行演示。

## 3. 四 Tab 网页

左上角固定四个 Tab：

1. 成功叉车：normal 证据。
2. 恢复叉车：recovery 证据。
3. 安全介入：intervention 证据。
4. Fast-WAM：只显示独立验证范围、现有日志和待补机械臂素材，不显示虚构叉车视频。

三个叉车 Tab 共用交互：

- 飞书风格 AgentOS 对话框。
- 预填任务来自当前运行的首个 `task_started` 事件。
- 点击“发送”后显示技能/Fallback 分发并播放演示片。
- 视频时间更新时，右侧显示当前事件对应指令；技能完成后显示从该事件派生的“审计表/任务状态更新”。
- 切换 Tab 时停止旧视频并清空旧状态，避免跨运行串帧。

Fast-WAM Tab 明确显示：

- 已验证：独立 action shape/推理接线证据（以仓库内现有日志为准）。
- 未验证：叉车控制、机械臂正式演示视频、企业设备部署。

## 4. 验收补充

- USD 场景可检索到 PhysicsScene、Collision、RigidBody、Mass、ArticulationRoot、FixedJoint 和 physics material binding。
- `physical_attachment_enabled` 只在载荷附着阶段为真，释放后为假。
- 三场景重新录制并维持原终态。
- 四个 Tab 可点击；三个叉车场景加载正确证据；Fast-WAM 不伪造视频。
- AgentOS 任务文本、当前指令和审计更新均能追溯到当前运行事件。
- 文档列出真实叉车模型、飞书现场录屏和 Fast-WAM 机械臂素材三个待协助项。
