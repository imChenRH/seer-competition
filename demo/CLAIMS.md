# Demo 声明—证据矩阵

标签定义：`VERIFIED` 已由本仓库或随附证据复验；`DEMO_IMPLEMENTED` 演示级实现，不等于生产；`PAPER_METRIC` 仅引用论文；`NOT_IMPLEMENTED` 尚未实现。

| 声明 | 状态 | 可接受表述 | 证据 |
|---|---|---|---|
| 九技能任务分解与审计 | VERIFIED | Aily/状态机按固定九技能编排，并产生连续事件 | `tests/test_engine.py`；各运行 `events.jsonl` |
| Fallback 自动恢复 | VERIFIED | recovery 场景首次偏移失败，执行 FB-F01 后第二次通过 | recovery JSONL 与视频 |
| 安全停车和人工介入 | VERIFIED | intervention 场景三次遮挡失败，FB-F07 退回并停稳 | intervention JSONL 与视频 |
| Isaac Sim 执行 | DEMO_IMPLEMENTED | Isaac Sim 6.0.1 中以确定性运动目标驱动的可重复数字孪生 | `demo/seer_demo/isaac/`、scene/video/summary |
| USD 物理语义 | VERIFIED | 正式 USDA 写入 PhysicsScene、CollisionAPI、RigidBodyAPI、MassAPI 与 FixedJoint；关节局部锚点与车体/载荷变换一致，载荷释放后从 PhysX 世界变换观测 | `scene.usda`、`summary.physics_contract`、正式运行日志 |
| 静态设施碰撞 | VERIFIED | 七类常驻设施具有静态碰撞；故障障碍物仅在 intervention 启用，normal/recovery 不保留隐形碰撞体。V5 normal/recovery 各验证 193 个静态碰撞 Prim，V6 intervention 为 195 个 | 正式 `summary.static_physics_contract`、`summary.static_collision_prim_count`、`tests/test_timeline.py` |
| 载荷叉取与放置 | DEMO_IMPLEMENTED | 两个叉孔与货叉对齐；只有相对几何满足且 `FixedJoint` 启用才报告挂接；放置时降低、释放并等待受支撑载荷停稳 | normal/recovery JSONL 的 `physical_attachment_enabled`、`payload_supported`、`payload_settled`，USDA 与视频 |
| 场景比例与路径对齐 | VERIFIED | 车轮落地；集装箱为 7.5×3.4×3.5 m；11 根横向圆柱滚筒组成传送带；集装箱和传送带均与地面黄线平行 | 三份 `scene.usda`、`summary.facility_layout`、`tests/test_timeline.py`、正式视频 |
| 防穿模扫掠守卫 | DEMO_IMPLEMENTED | `2.5D_OBB_SAT_SWEEP_V4` 对车身、四轮、倾斜叉架、双货叉、12 部件载荷、齐平集装箱地板、圆柱滚筒和 intervention 障碍物包络做扫掠检查；V5 normal/recovery 与 V6 intervention 的障碍物穿透、禁碰数、接触违规数均为 0，最小车身净距不低于 0.213986 m；这不等于完整动力学或生产安全认证 | 正式 `summary.json` / `MANIFEST.json`、`demo/seer_demo/isaac/collision.py`、`tests/test_timeline.py` |
| 侧前方联动镜头 | DEMO_IMPLEMENTED | 相机位于叉车局部前半平面并保留侧向夹角；近距交互时把未连接货物纳入主体包络，三场景完整叉车与相关货物解析边距不低于 5% | `summary.camera_strategy`、`simulation.mp4`、`demo/seer_demo/isaac/scene.py`、`tests/test_timeline.py` |
| 双层架构展示 | DEMO_IMPLEMENTED | 左侧 Isaac 操作与右侧可审计的结构化决策摘要使用同一 `observed_frame / fps` 视频帧时钟；运行/恢复/完成/人工接管用蓝/琥珀/绿/红主题；右侧不是隐藏思维过程 | `presentation.mp4`、`demo/seer_demo/presentation.py`、`tests/test_presentation.py` |
| 飞书 → Isaac 闭环 | DEMO_IMPLEMENTED | 同主机/同证据目录的单实例桥接可认领、一次启动、以哈希收据恢复回放；操作员见证回执对应 `T-DEMO-20260813-001`，不是三份 2026-08-15 正式录像的现场见证 | `tests/test_bridge.py`；经 manifest 哈希的操作员见证回执（不是飞书签名证明） |
| Fast-WAM 能加载推理 | VERIFIED | 独立技术验证输出形状 `[1,7]`，首次单次约 0.86 s | 经顶层 manifest 哈希的脱敏验证日志 |
| Fast-WAM 黑碗→盘操作 | VERIFIED | 在官方 LIBERO `libero_goal` task 8、五个固定初态和 300 步预算下，原版 `env.check_success()` 通过 5/5；五次均由 revision 与 SHA-256 已绑定的 checkpoint 在 77–84 个 7D 动作内完成。该数字只描述随附固定初态，不是通用成功率或完整基准 | `fastwam-bowl-plate-20260816-v2-r1` 的五组视频/动作/状态、事件、模型指纹、摘要、公共格式分屏片与 Manifest 哈希 |
| Fast-WAM 190 ms | PAPER_METRIC | 论文报告指标，未在本机复现 | 论文引用；不得写成 Demo 实测 |
| Fast-WAM 控制叉车 | NOT_IMPLEMENTED | 当前不控制；需叉车数据、后训练和安全门控 | 无 |
| ROS 2 真实闭环 | NOT_IMPLEMENTED | 当前桥接为进程/API 边界，不宣称 ROS 2 | 无 |
| 仙工 SRC-5000 实机控制 | NOT_IMPLEMENTED | 仅是未来企业接口目标 | 无 |
| 真实 RGB-D/雷达感知 | NOT_IMPLEMENTED | 当前异常由确定性场景条件产生 | 无 |
| 动力学/轮胎/载荷标定 | NOT_IMPLEMENTED | 当前虽有 USD 物理 schema 与显式挂接，仍无企业参数标定，不代表真实叉车性能 | 无 |

## 禁止出现在正式演示中的无条件说法

- “Fast-WAM 正在实时控制这台叉车”
- “190 ms 是我们在这台 4090 上测得的延迟”
- “已经接入 SRC-5000 实机”
- “ROS 2 物理闭环已完成”
- “视频证明了生产级安全”
- “成功率 100%”——除非明确限定为某组已验证运行的结果，而不是系统泛化成功率
- “Fast-WAM 已达到通用 100% 成功率”或“5/5 是完整官方 LIBERO 基准成绩”
