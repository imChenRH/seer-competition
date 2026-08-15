# 正式证据包

本目录收录 2026-08-15 在 AutoDL RTX 4090 / Isaac Sim 6.0.1 上重新生成、下载到 Mac 并复验的正式证据。

- `isaac-normal-20260815-v2-r4/`：529 帧、66.125 秒视频、20 条事件，终态 `COMPLETED`。
- `isaac-recovery-20260815-v2-r4/`：617 帧、77.125 秒视频、24 条事件，包含 `FB-F01`，终态 `COMPLETED`。
- `isaac-intervention-20260815-v2-r4/`：289 帧、36.125 秒视频、18 条事件；两次 `FB-F02` 后执行 `FB-F07`，车辆退至箱外并停稳，终态 `HUMAN_REQUIRED`。
- `MANIFEST.json`：由 `scripts/build_evidence_manifest.py` 重验 JSONL 与视频后生成，并对飞书回执和 Fast-WAM 独立材料记录文件大小与 SHA-256。
- `FEISHU_LIVE_RECEIPT.json`：现场任务 `T-DEMO-20260813-001` 的脱敏操作员见证回执；它不是飞书签名或不可伪造的 API 导出。
- `fastwam/`：Fast-WAM 单批加载/推理的独立验证；不能当作叉车控制证据。

每个正式目录同时包含原始 `simulation.mp4` 与 2560×1080 的 `presentation.mp4`。后者把 1280×720 仓库内部操作放在左半屏，右半屏按同一视频帧时钟渲染任务目标、大脑技能分发、小脑执行、Fallback、安全门和审计事件；右侧是结构化、可复算的决策摘要，不是隐藏思维过程。正式分屏使用显式 CJK 字体生成，渲染器在缺少中文字体时会失败关闭，不再生成方框字。

三场景均由 `2.5D_OBB_SAT_SWEEP_V2` 认证：normal、recovery、intervention 分别执行 859,140、960,798、547,824 次 Z 区间相交后的 SAT 候选检查，禁止碰撞与接触违规均为 0；normal/recovery 最小车身净距为 0.150441 m，intervention 为 0.256748 m。normal/recovery 各包含 206 个静态碰撞 Prim，intervention 因启用故障障碍物包含 208 个。

录像展示的是确定性运动目标驱动的数字孪生。正式 USDA 保存基座、偏航角、门架、货叉倾斜、载荷与 `PhysicsFixedJoint` 的时间采样，并写入 PhysicsScene、碰撞、刚体、质量及物理材质绑定。JSONL 的 `payload_attached=true` 同时要求相对几何满足且 `physical_attachment_enabled=true`。这仍是明确标注的演示降级：运动学基座上的 ArticulationRoot schema 在 PhysX 中不会形成有效关节动力学闭环，异常场景也是确定性注入，车辆动力学、轮胎、载荷和制动没有企业参数标定；它不是实机、ROS 2、校准力控或生产安全验证。
