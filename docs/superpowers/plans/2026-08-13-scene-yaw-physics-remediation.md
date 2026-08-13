# Scene Yaw and Physics Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除明显设施穿模，加入可见 yaw 对准，并以机器可核验契约说明场景的动态与静态物理角色。

**Architecture:** 时间线负责世界坐标、yaw 与安全路径；场景模块负责设施 Xform、USD 物理角色和位姿采样；观测模块从实测旋转与几何关系判断载荷状态。正式 Isaac 运行重新生成所有证据。

**Tech Stack:** Python 3.11、OpenUSD/UsdPhysics、Isaac Sim 6.0.1、unittest、FFmpeg。

## Global Constraints

- 叉车仍标为运动学控制，不得宣称真实动力学闭环。
- 设施静态碰撞体不添加不必要的 RigidBodyAPI。
- 所有生产逻辑先有会失败的行为测试。
- 三种场景必须保持 NORMAL/RECOVERY 完成与 INTERVENTION 人工介入终态。

---

### Task 1: Layout and physics contract

**Files:**
- Modify: `demo/seer_demo/isaac/scene.py`
- Test: `tests/test_timeline.py`

**Interfaces:**
- Produces: `warehouse_layout_spec() -> WarehouseLayoutSpec`
- Produces: `static_physics_contract() -> tuple[StaticPhysicsSpec, ...]`

- [x] 写失败测试，断言集装箱 `8°`、输送线 `-6°`、两者相距且横向错开，并断言 Ground/Warehouse/Racks/Container/LoadingDock/Conveyor/BackgroundLoads/Obstacle 都是静态碰撞角色。
- [x] 运行 `PYTHONPATH=demo python3 -m unittest tests.test_timeline -v`，确认因为接口缺失或旧布局而失败。
- [x] 实现不可变布局/物理契约，并让 `build_scene` 从该契约创建设施根节点和碰撞几何。
- [x] 重跑聚焦测试直到通过。

### Task 2: Yaw-aware timeline and observation

**Files:**
- Modify: `demo/seer_demo/isaac/timeline.py`
- Modify: `demo/seer_demo/isaac/scene.py`
- Modify: `demo/seer_demo/isaac/runner.py`
- Test: `tests/test_timeline.py`

**Interfaces:**
- `FrameState.yaw_deg: float`
- `derive_kinematic_observation(..., yaw_deg: float, ...) -> dict[str, object]`

- [x] 写失败测试，断言时间线同时出现正 yaw 与负 yaw、精确接近末端对齐 `8°`、输送线对齐末端为 `-6°`，且旋转载荷的局部偏移仍被识别为附着。
- [x] 运行聚焦测试并确认旧代码因 yaw 恒为零/观测不接收 yaw 而失败。
- [x] 给 `_Pose`/`_Segment` 加 yaw，插值 yaw；按旋转后的前向向量计算附着载荷世界坐标；`apply_frame` 写入 Z 轴旋转采样；观测使用实测 yaw。
- [x] 重跑时间线和运行器测试，修复所有调用点。

### Task 3: Evidence regeneration

**Files:**
- Modify: `demo/evidence/isaac-*/scene.usda`
- Modify: `demo/evidence/isaac-*/simulation.mp4`
- Modify: `demo/evidence/isaac-*/events.jsonl`
- Modify: `demo/evidence/isaac-*/summary.json`
- Modify: `demo/evidence/isaac-*/presentation.mp4`
- Modify: `demo/evidence/MANIFEST.json`

- [x] 本地运行纯 Python 回归和场景预览，确认路径/姿态契约成立。
- [x] 将代码同步到 Isaac 6.0.1 环境，分别运行 normal、recovery、intervention 正式渲染。
- [x] 下载并逐帧检查叉车车身不穿过集装箱、月台或输送线，yaw 在对准阶段可见。
- [x] 重建三套分屏视频与 Manifest，运行哈希校验。
