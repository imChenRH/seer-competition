# 正式证据包

本目录收录 2026-08-16 在 AutoDL RTX 4090 上重新生成、下载到 Mac 并复验的正式证据；叉车场景使用 Isaac Sim 6.0.1，机械臂场景使用 LIBERO/MuJoCo 与 Fast-WAM。

- `isaac-normal-20260816-v5-r1/`：531 帧、66.375 秒视频、20 条事件，终态 `COMPLETED`。
- `isaac-recovery-20260816-v5-r1/`：619 帧、77.375 秒视频、24 条事件，包含 `FB-F01`，终态 `COMPLETED`。
- `isaac-intervention-20260816-v6-r1/`：289 帧、36.125 秒视频、18 条事件；两次 `FB-F02` 后执行 `FB-F07`，车辆退至箱外并停稳，终态 `HUMAN_REQUIRED`；两块故障障碍物底面落地并保持 0.05 m 间隙。
- `fastwam-bowl-plate-20260816-v2-r1/`：官方 LIBERO task 8 的五个固定初态，300 步预算内 5/5 通过原版成功谓词；五次执行 77–84 步，并保留五组视频、动作和状态。摘要同时绑定模型仓库、revision、config SHA-256 和 weights SHA-256。
- `MANIFEST.json`：由 `scripts/build_evidence_manifest.py` 重验 JSONL、原始视频与分屏视频后生成，并记录文件大小和 SHA-256。
- `FEISHU_LIVE_RECEIPT.json`：现场任务 `T-DEMO-20260813-001` 的脱敏操作员见证回执；它不是飞书签名或不可伪造的 API 导出，也不是本轮三份录像的现场见证。
- `fastwam/`：Fast-WAM 单批加载/推理的独立验证；不能当作叉车控制证据。

每个正式目录同时包含原始 `simulation.mp4` 与 2560×1080 的 `presentation.mp4`。后者把 1280×720 仿真操作放在左半屏，右半屏按 `observed_frame / fps` 投影任务目标、大脑技能分发、小脑规控/策略执行、Fallback、安全门和审计事件。四种模式共享同一组 TASK、BRAIN、CEREBELLUM、SAFETY、AUDIT 卡片；运行、恢复、完成、人工接管分别使用明显不同的蓝、琥珀、绿、红主题。右侧是结构化、可审计的决策摘要，不是隐藏思维过程。

V5 场景使用落地圆柱车轮、顶面与世界地面齐平的集装箱地板、7.5×3.4×3.5 m 集装箱、11 根横向圆柱滚筒传送带，以及与地面黄线平行的集装箱和传送带。13 mm 侧前方动态跟随机位按叉车局部坐标构图；近距识别、插叉、抬升、搬运与放置阶段同时纳入货物包络。机位限制在货架之间、集装箱后墙前方和顶梁下方；完整叉车与相关货物的解析投影边距在三场景均不低于 5%。

三场景均由显式包含四个轮胎包络的 `2.5D_OBB_SAT_SWEEP_V4` 认证：normal、recovery、intervention 分别执行 1,128,953、1,248,809、651,784 次 Z 区间相交后的 SAT 候选检查，障碍物相互穿透、禁止碰撞与接触违规均为 0；最小车身净距分别为 0.213986、0.213986、0.387376 m。normal/recovery 各包含 193 个静态碰撞 Prim，intervention 因启用故障障碍物包含 195 个。

录像展示的是确定性运动目标驱动的数字孪生。正式 USDA 写入 PhysicsScene、CollisionAPI、RigidBodyAPI、MassAPI、FixedJoint、物理材质绑定和时间采样；FixedJoint 的局部锚点随实际车体/载荷变换保持一致，载荷释放后从 PhysX 世界变换读取位置与朝向。该证据仍不是实机、ROS 2、校准力控、完整轮胎动力学或生产安全验证。
