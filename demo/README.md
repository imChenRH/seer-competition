# SEER–HVLA 叉车卸货 Demo

项目目标、架构、完成内容、正式证据、企业展示流程和下一阶段计划统一汇总于 [`项目总结与交付说明.md`](项目总结与交付说明.md)；本轮四项升级的逐项验收、降级说明和待人类输入见 [`UPGRADE-REPORT-2026-08-15.md`](UPGRADE-REPORT-2026-08-15.md) 与 [`NEEDS-HUMAN.md`](NEEDS-HUMAN.md)。

这是一个**证据驱动的企业交流 Demo**：Aily/飞书负责生成和认领任务，单进程桥接只启动一次 Isaac runner；Isaac Sim 6.0.1 使用确定性运动目标与显式 `UsdPhysics.FixedJoint` 载荷挂接；每一步把实际观测写入连续 JSONL；网页从 JSONL 与录像还原大脑—小脑分发过程。界面参考随附的 [`agentos对话模版.png`](agentos对话模版.png)：初始只呈现四种模式与 AgentOS 对话，发送指令后才展开运行证据。

> 2026-08-16 V5/V6 已完成正式重渲染：四个圆柱车轮贴地，集装箱地板顶面与世界地面齐平，集装箱扩大到 7.5×3.4×3.5 m，传送带使用 11 根横向圆柱滚筒，设施与黄线平行；13 mm 侧前方动态跟随机位把完整叉车与近距交互货物纳入同一主体包络，并避开货架、集装箱后墙和顶梁。安全介入 V6 将两块故障障碍物改为共用的显式几何定义，底面都落在地面上且保持 0.05 m 间隙。三场景真实 Isaac 录像、USDA、JSONL、分屏片和 manifest 已在 Mac 复验，障碍物穿透、禁止碰撞与接触违规均为 0。该结论只适用于随附三次演示运行，不外推为生产安全认证。

> 2026-08-16 Fast-WAM 操作轨迹已切换到官方 LIBERO `libero_goal` task 8 `put_the_bowl_on_the_plate`：`lerobot/fastwam_libero_uncond_2cam224` revision `53983e1` 的本地 checkpoint 已通过 config/weights SHA-256 绑定，并在 RTX 4090 上生成全部 7D 动作；五个固定初态都在 300 步预算内通过原版 `env.check_success()`，实际执行 77–84 步。五次视频、动作、状态、公共格式分屏片和哈希均保存于 `fastwam-bowl-plate-20260816-v2-r1`。5/5 只描述这五个固定初态，不外推为通用成功率或完整官方基准成绩。

当前工程采用“局部重构”路线。业务场景、九技能、Fallback、飞书表、AutoDL/Isaac 环境与 Fast-WAM 独立验证继续保留；旧执行器、旧桥接与硬编码网页不再作为正式证据。严格审计见 [`AUDIT.md`](AUDIT.md)，对外声明边界见 [`CLAIMS.md`](CLAIMS.md)。

## 当前能证明什么

- normal：九技能按顺序执行；只有托盘几何对齐且 `FixedJoint` 已启用才报告叉取，释放后关节关闭，终态为 `COMPLETED`。
- recovery：首次栈板对位失败，执行 `FB-F01` 横向修正，第二次通过，终态为 `COMPLETED`。
- intervention：三次遮挡失败，执行 `FB-F02` 与 `FB-F07`，车辆退回并停稳，终态为 `HUMAN_REQUIRED`。
- Fast-WAM 操作：官方碗→盘任务的五个固定 seed 均通过原版 `env.check_success()`；页面展示第 0 次轨迹，并同时列出 5 次完整结果。它只证明随附固定初态，不是叉车控制、通用成功率或完整基准复现。
- 所有结果均来自同一事件契约；序号连续、仿真时间单调，且最后只有一个终态事件。
- 分屏右栏按 `observed_frame / fps` 的视频帧时钟投影事件；无观测帧的启动事件继承前一观测边界，因此右侧摘要不会在左侧视频完成动作前提前显示完成。
- 桥接层在同一主机、同一证据目录内持有进程排他锁，再对任务进行乐观认领；未通过整批事件校验时不会写成成功。
- 三份正式场景把叉车 Z 轴偏航、设施局部坐标路径和载荷相对位置写入同一时间线；集装箱与传送带均和地面黄线平行。地面、外壳、货架、集装箱、月台、传送带、背景载荷七类常驻设施具有碰撞，故障障碍物仅在 intervention 可见且启用碰撞，normal/recovery 不保留隐形碰撞体。
- 新时间线在生成、Isaac 每帧写入、分屏合成和 Manifest 四个边界失败关闭；车身/四轮/载荷平移和升降步长不大于 0.025 m，车身/载荷偏航和货叉倾角步长不大于 0.5°。载荷按 5 根 deck、3 根 runner 和 4 个 cargo 独立检查，只有方向正确、误差受限的支撑接触被允许。`2.5D_OBB_SAT_SWEEP_V4` 正式结果：normal 1128953 次、recovery 1248809 次、intervention 651784 次候选对检查，三者障碍物穿透、禁碰数和接触违规数均为 0；水平放置误差为 0。

它**不能**证明生产级动力学、安全、感知、ROS 2、仙工 SRC-5000 实机控制，也不能证明 Fast-WAM 已控制叉车。当前控制方式是“确定性运动目标 + 显式物理挂接”的可重复演示降级，不是标定力控；异常由场景条件注入。

## 本地检查与展示

无需 Isaac Sim，也不需要 GPU。本地模式用于验证状态机、事件契约、桥接逻辑和操作台；`check`/`generate`/`serve` 可在 macOS、Linux 或 Windows Git Bash 中执行。

```bash
cd <repository>
./scripts/run_demo.sh check
./scripts/run_demo.sh generate demo/evidence/local
./scripts/run_demo.sh serve demo/evidence/local 8765
```

浏览器打开 `http://127.0.0.1:8765`。页面初始不会展示旧运行详情；选择模式并发送指令后，才加载对应证据与视频。页面不会自行生成“成功率”或“延迟”；没有有效 `summary.json` 与 `events.jsonl` 的目录不会被展示。

选择“Fast-WAM 碗→盘”，发送“把黑色碗放入盘子”后，页面会加载 `fastwam-bowl-plate-20260816-v2-r1/presentation.mp4`。Fast-WAM 与前三个模式复用同一证据区、技能/Fallback/审计组件和右侧分层卡片。本地播放不需要 GPU；重新运行模型才需要 Linux、CUDA、LIBERO/MuJoCo 和 checkpoint。

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
presentation.mp4 左侧仿真、右侧大脑/小脑与审计摘要的同步展示视频
```

`frames/` 是可再生成的中间文件，不需要提交 Git。

如需在 Mac 重新合成左右分屏视频，先为渲染工具安装唯一的 Python 依赖，并确认系统存在 `ffmpeg`/`ffprobe`：

```bash
python3 -m venv .venv-presentation
.venv-presentation/bin/pip install -r demo/requirements-presentation.txt
.venv-presentation/bin/python scripts/build_split_presentation.py \
  demo/evidence/isaac-normal-20260816-v5-r1
```

脚本会验证原始片与演示片的帧率、帧数、时长和 2560×1080 分辨率，再更新对应 `summary.json`；不会把左右两侧使用不同时间轴的视频写成正式证据。渲染中文需要 macOS 的 PingFang/STHeiti、Linux 的 Noto Sans CJK，或通过 `--font /path/to/cjk-font` 显式指定；缺少 CJK 字体时脚本失败关闭，不生成方框字视频。

## 飞书桥接

凭证只放在本地 `demo/.env`，模板见 `demo/.env.example`。必须为同一部署长期配置稳定的 `BRIDGE_ID`。任务表除现有字段外增加数值字段 `最后事件序号`，用于幂等回写；审计表按事件唯一 ID 追加。桥接在**同一主机和同一证据目录**中用排他文件锁强制单实例（POSIX 使用 `flock`，Windows 使用 `msvcrt` 字节锁），再使用飞书字段做乐观认领和断点续传；它不是跨主机、跨数据中心的事务队列或分布式租约。

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

1. 先说明边界：当前是确定性运动目标与显式载荷挂接的 Isaac Demo，不是实机或 Fast-WAM 闭环。
2. 在 AgentOS 输入框发送 normal 的已验证任务，展示大脑层意图、技能分发、小脑层执行与审计游标同步推进。
3. 播放 `presentation.mp4`：左半屏是仓库内部操作，右半屏是结构化决策摘要，不展示隐藏思维过程。
4. 切换“自动恢复”，指出第一次失败、`FB-F01` 与第二次成功的同源事件。
5. 切换“安全介入”，指出三次失败、退回、停稳以及 `HUMAN_REQUIRED`；不要把它说成完成。
6. 切换“Fast-WAM 碗→盘”，发送黑碗任务，展示模型动作、物理误差、官方成功终帧和 5/5 固定初态结果；明确这不是通用成功率或完整基准，模型也没有接管叉车。
7. 向仙工确认实机接口：底盘/门架/货叉指令、状态频率、坐标系、急停、安全 PLC、仿真模型和日志格式。

## 验证

当前 `run_demo.sh check` 在 macOS/Linux 上包含 198 项 Python 测试；Windows 上仅跳过依赖 macOS JavaScriptCore 的协议执行测试。独立 JavaScript 协议脚本包含 48 项断言。

```bash
./scripts/run_demo.sh check
PYTHONPATH=demo python3 -m seer_demo.cli validate \
  demo/evidence/<run-id>/events.jsonl
```

提交前还应校验录像帧数、清单 SHA-256、浏览器控制台、凭证泄露和飞书现场任务记录。仓库 `.gitattributes` 将 Python、Markdown、JSON/JSONL、USDA 与前端源码统一为 LF，避免 Windows 检出改写证据文件后导致 Manifest SHA-256 复验不一致。当前完成情况以根目录《待办事项.md》为准，历史《Demo制作规划.md》不再作为事实源。
