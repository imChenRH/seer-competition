# 正式证据包

本目录收录 2026-08-13 在 AutoDL RTX 4090 / Isaac Sim 6.0.1 上生成并在 Mac 下载复验的证据。

- `isaac-normal-20260813/`：457 帧，57.125 秒，20 条事件，终态 `COMPLETED`。
- `isaac-recovery-20260813/`：545 帧，68.125 秒，24 条事件，包含 `FB-F01`，终态 `COMPLETED`。
- `isaac-intervention-20260813/`：289 帧，36.125 秒，18 条事件；两次 `FB-F02` 调整均有完成事件，车辆退至箱外 `x=-1.0` 并停稳，终态 `HUMAN_REQUIRED`。
- `MANIFEST.json`：由 `scripts/build_evidence_manifest.py` 重验 JSONL 与视频后生成，并对飞书回执和 Fast-WAM 独立材料一并记录文件大小与 SHA-256。
- `FEISHU_LIVE_RECEIPT.json`：现场任务 `T-DEMO-20260813-001` 的脱敏操作员见证回执；它不是飞书签名或不可伪造的 API 导出。
- `fastwam/`：Fast-WAM 单批加载/推理的独立验证，已纳入顶层 manifest；不能当作叉车控制证据。

每个正式目录同时包含原始 `simulation.mp4` 与 2560×1080 的 `presentation.mp4`。后者把 1280×720 仓库内部操作等比例放在左半屏，右半屏按同一仿真时间渲染大脑意图、小脑技能、Fallback、安全门和审计事件；右侧是结构化、可复算的决策摘要，不是隐藏思维过程。

录像展示的是确定性运动目标驱动的数字孪生。正式 USDA 保存基座、偏航角、门架、货叉倾斜、载荷与 `PhysicsFixedJoint` 的时间采样，并写入 PhysicsScene、碰撞、刚体、质量及物理材质绑定。地面、仓库外壳、货架、集装箱、月台、传送带、背景载荷和障碍物八类设施均执行静态碰撞契约；本轮三份场景各验证到 186 个碰撞 Prim。叉车和活动托盘是运动对象，灯光、相机、路径标线与材质引用不是碰撞对象。JSONL 的 `payload_attached=true` 同时要求相对几何满足且 `physical_attachment_enabled=true`。这仍是明确标注的演示降级：运动学基座上的 ArticulationRoot schema 在 PhysX 中不会形成有效关节动力学闭环，异常场景也是确定性注入，车辆动力学、轮胎、载荷和制动没有企业参数标定；它不是实机、ROS 2、校准力控或生产安全验证。
