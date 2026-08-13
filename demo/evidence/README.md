# 正式证据包

本目录收录 2026-08-13 在 AutoDL RTX 4090 / Isaac Sim 6.0.1 上生成并在 Mac 下载复验的证据。

- `isaac-normal-20260813/`：409 帧，51.125 秒，20 条事件，终态 `COMPLETED`。
- `isaac-recovery-20260813/`：497 帧，62.125 秒，24 条事件，包含 `FB-F01`，终态 `COMPLETED`。
- `isaac-intervention-20260813/`：289 帧，36.125 秒，18 条事件；两次 `FB-F02` 调整均有完成事件，车辆退至箱外 `x=-1.0` 并停稳，终态 `HUMAN_REQUIRED`。
- `MANIFEST.json`：由 `scripts/build_evidence_manifest.py` 重验 JSONL 与视频后生成，并对飞书回执和 Fast-WAM 独立材料一并记录文件大小与 SHA-256。
- `FEISHU_LIVE_RECEIPT.json`：现场任务 `T-DEMO-20260813-001` 的脱敏操作员见证回执；它不是飞书签名或不可伪造的 API 导出。
- `fastwam/`：Fast-WAM 单批加载/推理的独立验证，已纳入顶层 manifest；不能当作叉车控制证据。

录像展示的是确定性规则控制的运动学数字孪生。正式 USDA 保存基座、门架、货叉倾斜与载荷的 `xformOp` 时间采样；JSONL 中角度、位置、载荷耦合、障碍可见性和停车速度从这些实际场景变换/visibility 推导。终态事件复用最后一个决策事件的场景读回与观测帧，严格验证二者一致；原视频和 USDA 未因这一事件契约升级而改写。异常场景布局仍是确定性注入，不是真实传感器。它不是实机、ROS 2、校准动力学或生产安全验证。
