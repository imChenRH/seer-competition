# SEER–HVLA 叉车卸货 Demo

这是一个**证据驱动的企业交流 Demo**：Aily/飞书负责生成和认领任务，单进程桥接只启动一次 Isaac runner；Isaac Sim 6.0.1 运行规则控制的运动学数字孪生；每一步把实际观测写入连续 JSONL；只读网页从 JSONL 与录像还原结果。

当前工程采用“局部重构”路线。业务场景、九技能、Fallback、飞书表、AutoDL/Isaac 环境与 Fast-WAM 独立验证继续保留；旧执行器、旧桥接与硬编码网页不再作为正式证据。严格审计见 [`AUDIT.md`](AUDIT.md)，对外声明边界见 [`CLAIMS.md`](CLAIMS.md)。

## 当前能证明什么

- normal：九技能按顺序执行，载荷的耦合、搬运与释放由 USD 几何关系观测，终态为 `COMPLETED`。
- recovery：首次栈板对位失败，执行 `FB-F01` 横向修正，第二次通过，终态为 `COMPLETED`。
- intervention：三次遮挡失败，执行 `FB-F02` 与 `FB-F07`，车辆退回并停稳，终态为 `HUMAN_REQUIRED`。
- 所有结果均来自同一事件契约；序号连续、仿真时间单调，且最后只有一个终态事件。
- 桥接层在同一主机、同一证据目录内持有进程排他锁，再对任务进行乐观认领；未通过整批事件校验时不会写成成功。

它**不能**证明生产级动力学、安全、感知、ROS 2、仙工 SRC-5000 实机控制，也不能证明 Fast-WAM 已控制叉车。当前控制器是确定性规则控制的运动学数字孪生，载荷采用显式耦合；异常由场景条件注入。

## Mac 上运行

无需 Isaac Sim，也不需要 GPU。Mac 模式用于验证状态机、事件契约、桥接逻辑和操作台。

```bash
cd <repository>
./scripts/run_demo.sh check
./scripts/run_demo.sh generate demo/evidence/local
./scripts/run_demo.sh serve demo/evidence/local 8765
```

浏览器打开 `http://127.0.0.1:8765`。页面不会自行生成“成功率”或“延迟”；没有有效 `summary.json` 与 `events.jsonl` 的目录不会被展示。

## Isaac Sim 正式运行

在已安装 Isaac Sim 6.0.1 与 ffmpeg 的 Linux/GPU 环境执行：

```bash
ISAAC_SIM_ROOT=/path/to/isaacsim601 \
  ./scripts/run_isaac_demo.sh \
  normal \
  demo/evidence/isaac-normal \
  isaac-normal-001
```

分别把 `normal` 改为 `recovery`、`intervention`。每个证据目录必须包含：

```text
events.jsonl     连续、可机器验证的唯一事实源
summary.json     从 JSONL 验证结果派生的摘要
scene.usda       此次运行导出的 OpenUSD 场景
simulation.mp4   与此次运行一致的 Isaac 录像
```

`frames/` 是可再生成的中间文件，不需要提交 Git。

## 飞书桥接

凭证只放在本地 `demo/.env`，模板见 `demo/.env.example`。必须为同一部署长期配置稳定的 `BRIDGE_ID`。任务表除现有字段外增加数值字段 `最后事件序号`，用于幂等回写；审计表按事件唯一 ID 追加。桥接在**同一主机和同一证据目录**中用排他文件锁强制单实例，再使用飞书字段做乐观认领和断点续传；它不是跨主机、跨数据中心的事务队列或分布式租约。

新任务只允许写入全新的 `task_id` 目录。runner 成功后才以四个产物的 SHA-256 一次写入本地 `.runner-complete.json`；它是篡改单个文件时可检出的恢复收据，不是文件系统不可变、签名封印或外部可信时间戳。桥接重启时只能验证该收据并回放未写入的审计事件，绝不重启 runner；若进程在收据生成前中断，原任务失败关闭，操作员必须创建带新任务 ID 的显式 retry。

正式任务链路：

```text
Aily/飞书待执行任务
  → 桥接认领并写“执行中”
  → 只启动一次 Isaac runner
  → 完整产物哈希封存
  → 校验整批 JSONL
  → 按序写审计与最后事件序号
  → 仅根据终态写“已完成”或“需人工”
```

## 建议的 6–8 分钟企业展示

1. 先说明边界：当前是 Isaac 运动学数字孪生，不是实机或 Fast-WAM 闭环。
2. 在飞书/Aily 创建 normal 任务，展示任务被认领且只运行一次。
3. 打开操作台，同时展示录像、九技能时间线与连续审计事件。
4. 切换 recovery，指出第一次失败、`FB-F01` 与第二次成功的同源事件。
5. 切换 intervention，指出三次失败、退回、停稳以及 `HUMAN_REQUIRED`；不要把它说成完成。
6. 单独展示 Fast-WAM 加载与 `[1,7]` 输出证据，明确它尚未接管叉车。
7. 向仙工确认实机接口：底盘/门架/货叉指令、状态频率、坐标系、急停、安全 PLC、仿真模型和日志格式。

## 验证

```bash
./scripts/run_demo.sh check
PYTHONPATH=demo python3 -m seer_demo.cli validate \
  demo/evidence/<run-id>/events.jsonl
```

提交前还应校验录像帧数、清单 SHA-256、浏览器控制台、凭证泄露和飞书现场任务记录。当前完成情况以根目录《待办事项.md》为准，历史《Demo制作规划.md》不再作为事实源。
