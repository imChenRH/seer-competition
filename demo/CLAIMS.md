# Demo 声明—证据矩阵

标签定义：`VERIFIED` 已由本仓库或随附证据复验；`DEMO_IMPLEMENTED` 演示级实现，不等于生产；`PAPER_METRIC` 仅引用论文；`NOT_IMPLEMENTED` 尚未实现。

| 声明 | 状态 | 可接受表述 | 证据 |
|---|---|---|---|
| 九技能任务分解与审计 | VERIFIED | Aily/状态机按固定九技能编排，并产生连续事件 | `tests/test_engine.py`；各运行 `events.jsonl` |
| Fallback 自动恢复 | VERIFIED | recovery 场景首次偏移失败，执行 FB-F01 后第二次通过 | recovery JSONL 与视频 |
| 安全停车和人工介入 | VERIFIED | intervention 场景三次遮挡失败，FB-F07 退回并停稳 | intervention JSONL 与视频 |
| Isaac Sim 执行 | DEMO_IMPLEMENTED | Isaac Sim 6.0.1 中的规则控制运动学数字孪生 | `demo/seer_demo/isaac/`、scene/video/summary |
| 载荷叉取与放置 | DEMO_IMPLEMENTED | 载荷耦合和释放由 USD 相对几何位置推导，画面与状态事件一致 | normal/recovery JSONL 状态、带时间采样的 USDA 与视频 |
| 飞书 → Isaac 闭环 | DEMO_IMPLEMENTED | 同主机/同证据目录的单实例桥接可认领、一次启动、以哈希收据恢复回放 | `tests/test_bridge.py`；经 manifest 哈希的操作员见证回执（不是飞书签名证明） |
| Fast-WAM 能加载推理 | VERIFIED | 独立技术验证输出形状 `[1,7]`，首次单次约 0.86 s | 经顶层 manifest 哈希的脱敏验证日志 |
| Fast-WAM 190 ms | PAPER_METRIC | 论文报告指标，未在本机复现 | 论文引用；不得写成 Demo 实测 |
| Fast-WAM 控制叉车 | NOT_IMPLEMENTED | 当前不控制；需叉车数据、后训练和安全门控 | 无 |
| ROS 2 真实闭环 | NOT_IMPLEMENTED | 当前桥接为进程/API 边界，不宣称 ROS 2 | 无 |
| 仙工 SRC-5000 实机控制 | NOT_IMPLEMENTED | 仅是未来企业接口目标 | 无 |
| 真实 RGB-D/雷达感知 | NOT_IMPLEMENTED | 当前异常由确定性场景条件产生 | 无 |
| 动力学/轮胎/载荷标定 | NOT_IMPLEMENTED | 当前为运动学轨迹，不代表真实叉车性能 | 无 |

## 禁止出现在正式演示中的无条件说法

- “Fast-WAM 正在实时控制这台叉车”
- “190 ms 是我们在这台 4090 上测得的延迟”
- “已经接入 SRC-5000 实机”
- “ROS 2 物理闭环已完成”
- “视频证明了生产级安全”
- “成功率 100%”——除非明确限定为某组已验证运行的结果，而不是系统泛化成功率
