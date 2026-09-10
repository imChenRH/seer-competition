# SEER-HVLA

> An evidence-driven layered VLA demo for industrial forklift container unloading.
> Deterministic Isaac Sim digital twin, nine-skill AgentOS orchestration, fallback
> recovery, a collision-certified motion guard, and a read-only audit console.
> Every published number is derived from one sealed `events.jsonl` per run.

一个面向工业叉车集装箱卸货的**分层 VLA 演示系统**。它要回答的不是"模型能不能动"，而是工业现场真正会问的三个问题：**出了事能不能查、上线前能不能验、危险时能不能停。**

---

## 目录

- [问题与定位](#问题与定位)
- [分层架构](#分层架构)
- [核心设计：单一事实源](#核心设计单一事实源)
- [验证结果](#验证结果)
- [快速开始](#快速开始)
- [仓库结构](#仓库结构)
- [边界声明](#边界声明)
- [工程记录](#工程记录)

---

## 问题与定位

端到端 VLA 在实验室里已经能完成长序列操作，但工业场景有三个前提它不满足：失败可重来、无节拍约束、无安全合规要求。本项目的判断是——**VLA 做技能选择与目标参数生成（软决策），经典控制做轨迹执行与安全保护（硬执行）**，两者之间由任务编排与证据层连接。

因此本仓库的工程重心不在模型本身，而在**让模型输出可被验证**：

- VLA 只输出"做什么、做到什么程度"，不直接输出关节或底盘动作；
- 每一层都有一组可观测的后置条件谓词，谓词不成立就不能写成功；
- 所有判定结论都必须能从一个连续事件流重新推导出来。

## 分层架构

```
                        飞书 Aily（业务入口）
                               │  自然语言任务
                               ▼
        ┌──────────────────────────────────────────┐
        │  AgentOS 编排层（src/engine.py）           │
        │  九技能序列 · Fallback · 终态判定          │
        └──────────────────────────────────────────┘
                               │  技能 + 观测
                               ▼
        ┌──────────────────────────────────────────┐
        │  执行层                                   │
        │  Isaac Sim 数字孪生（src/isaac/）          │
        │  Fast-WAM 策略（src/fastwam/）             │
        │  确定性规则引擎（src/backends/dry_run.py） │
        └──────────────────────────────────────────┘
                               │  实际观测
                               ▼
        ┌──────────────────────────────────────────┐
        │  安全层（src/isaac/collision.py）          │
        │  2.5D OBB/SAT 扫掠碰撞认证 · 失败关闭      │
        └──────────────────────────────────────────┘
                               │
                               ▼
                  events.jsonl（唯一事实源）
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        飞书审计回写      证据清单哈希      只读证据控制台
       （src/bridge.py） （src/manifest.py）    （web/）
```

**九技能序列**（`src/scenarios.py`）：

```
FORK-NAV-01 进箱导航 → FORK-NAV-03 精确对位 → FORK-PER-01 栈板识别
→ FORK-OP-01 货叉插入 → FORK-OP-02 门架起升 → FORK-OP-03 货叉倾斜
→ FORK-NAV-02 月台区导航 → FORK-OP-05 传送带对接 → FORK-OP-04 栈板放置
```

**三个场景共用同一状态机**（`src/engine.py`），只有注入条件不同：

| 场景 | 注入条件 | Fallback | 终态 |
|---|---|---|---|
| `normal` | 无 | — | `COMPLETED` |
| `recovery` | 栈板横向偏移 0.25 m | `FB-F01` 重新识别与对位 | `COMPLETED` |
| `intervention` | 货物遮挡致三次识别失败 | `FB-F02` 调整视角 → `FB-F07` 退回安全点 | `HUMAN_REQUIRED` |

## 核心设计：单一事实源

这是本项目与普通演示最大的区别，也是代码的主要工作量所在。

**1. 事件契约是可验证的语义，不只是格式。** `src/contracts.py` 的 `validate_scenario_events()` 为三个场景各自硬编码了期望事件轨迹并逐条比对。它会拒绝：已 `skill_completed` 但状态谓词为假、伪造的 Fallback 观测、终态状态与前置决策不一致、`stopped=true` 却报告 `base_speed_mps=99`、`observed_frame` 非单调、序号不连续、终态不在末位。

**2. 每一层都把上层产物当作不可信输入重新校验。**

```
validate_scenario_events  →  assert_summary_matches_validation
                          →  assert_video_matches_summary（ffprobe 帧数）
                          →  build_manifest（重新校验 + SHA-256）
                          →  server 只暴露通过校验的运行目录
```

**3. 后端不能自己宣布成功。** `src/engine.py` 的注释即是设计约束：*backend executes actions but cannot invent success*。recovery 场景若首次尝试意外成功、intervention 若意外恢复，引擎直接抛 `RuntimeError`。安全停车失败时也不会产生"人工接管"终态。

**4. 物理判定需要两个条件同时成立。** 载荷叉取必须**同时**满足相对几何对齐与 `UsdPhysics.FixedJoint` 已启用，放置后关节关闭。抓取状态不由日志常量伪造。

**5. 运动安全性独立认证。** `src/isaac/collision.py` 实现纯 Python 的 2.5D OBB/SAT 扫掠守卫，把车身、四轮、倾斜叉架、双货叉、12 部件载荷与全部静态设施纳入逐帧检查；平移步长 ≤ 0.025 m、偏航步长 ≤ 0.5°。只允许方向正确、误差 ≤ 1 mm 的支撑面接触。时间线生成、Isaac 每帧写入、分屏合成、清单生成四处均失败关闭。

## 验证结果

以下数字全部来自 `evidence/MANIFEST.json` 封存的正式运行，可由 `python3 -m seer_demo.cli validate` 与 `bin/build_manifest.py` 独立复算。

| 场景 | 事件数 | 技能完成 | Fallback | 终态 | 碰撞候选对检查 | 最小车身净距 |
|---|---:|---:|---|---|---:|---:|
| `normal` | 20 | 9/9 | 0 | `COMPLETED` | 1,128,953 | 0.213986 m |
| `recovery` | 24 | 9/9 | `FB-F01` | `COMPLETED` | 1,248,809 | 0.213986 m |
| `intervention` | 18 | 2/9 | `FB-F02` `FB-F07` | `HUMAN_REQUIRED` | 651,784 | 0.387376 m |

三场景的障碍物穿透、禁止碰撞、接触违规计数均为 **0**；最大水平放置误差 **0**（上限 0.02 m）。

**Fast-WAM 策略验证**（`evidence/fastwam-bowl-plate-20260816-v2-r1/`）：官方 LIBERO `libero_goal` task 8 `put_the_bowl_on_the_plate`，五个固定初态在官方 300 步预算内 **5/5** 通过原版 `env.check_success()`，实际执行 77–84 步。全部 7D 动作由 revision 与 config/weights SHA-256 已绑定的 checkpoint 生成，无规则控制器补动作。

**测试**：202 项 Python 测试 + 56 项 JavaScript 协议断言。

> ⚠️ 5/5 只描述随附的五个固定初态，不是通用成功率，也不是完整官方基准复现。

## 快速开始

**本地展示不需要 GPU，也不需要 Isaac Sim** —— 展示使用仓库中已复验的正式录像与事件。

```bash
git clone <this-repo>
cd <this-repo>

./bin/demo.sh check                     # 202 项测试 + compileall + bash 语法检查
./bin/demo.sh serve evidence 8765       # 浏览器打开 http://127.0.0.1:8765
```

生成纯状态机干运行证据（不需要仿真环境）：

```bash
./bin/demo.sh generate evidence/local
./bin/demo.sh serve evidence/local 8765
```

单独校验一次运行的事件流：

```bash
PYTHONPATH=src python3 -m seer_demo.cli validate evidence/isaac-normal-20260816-v5-r1/events.jsonl
```

**需要真实仿真环境时**（Linux + GPU）：

```bash
# Isaac Sim 6.0.1
ISAAC_SIM_ROOT=/path/to/isaacsim601 ./bin/run_isaac.sh normal evidence/isaac-normal my-run-id

# Fast-WAM 策略（需要 Linux + CUDA + LIBERO/MuJoCo）
./bin/run_fastwam.sh <python> <model-dir> evidence/fastwam-run my-run-id
```

重新合成 2560×1080 双层同步展示视频（需要 `ffmpeg`/`ffprobe` 与 CJK 字体）：

```bash
pip install -r requirements-presentation.txt
python3 bin/build_presentation.py evidence/isaac-normal-20260816-v5-r1
```

回写飞书桥接需要的凭证放在仓库根的 `.env`（模板见 `.env.example`，已被 Git 忽略）。

> **本地校验的两个前提**
>
> - `bin/build_manifest.py` 会调用 `ffprobe` 重新探测视频帧数，这是重新封存证据的硬依赖；只跑测试与展示不需要它。
> - 若 checkout 路径含非 ASCII 字符（例如中文目录名），在部分 Windows 终端下 Python 解析 `PYTHONPATH` 会失败。此时请改用 ASCII 路径，或把 `src` 加入 `sys.path` 后再运行。

## 已验证状态

```
202 项 Python 测试通过          python -m unittest discover -s tests
                                 （1 项跳过：依赖 macOS JavaScriptCore 的前端协议测试，见 CI 的 macOS job）
56 项前端协议断言                tests/web_protocol_test.js
三个叉车事件流严格校验通过        20 / 24 / 18 条事件，终态 COMPLETED / COMPLETED / HUMAN_REQUIRED
Fast-WAM 证据包校验通过          5 次 attempt 的动作、状态、视频逐组交叉验证
evidence/ 全部 40 个封存文件       SHA-256 与 MANIFEST.json 逐字节一致
```


## 仓库结构

```
├── src/seer_demo/             核心包
│   ├── contracts.py           事件契约与严格语义校验
│   ├── engine.py              九技能状态机（唯一编排实现）
│   ├── scenarios.py           技能/Fallback 定义与状态谓词
│   ├── bridge.py              飞书单实例桥接（认领一次、执行一次、回放一次）
│   ├── feishu.py              飞书多维表格 API 边界
│   ├── manifest.py            证据清单、ffprobe 探测与 SHA-256 封存
│   ├── presentation.py        双层同步视频渲染
│   ├── server.py              只读证据 HTTP 服务（白名单 + Range）
│   ├── isaac/                 时间线、场景、观测、碰撞认证、正式 runner
│   ├── fastwam/               Fast-WAM 策略、LIBERO 场景与 rollout
│   └── backends/dry_run.py    确定性干运行后端（无需仿真环境）
├── web/                       只读证据控制台（零依赖、零构建、CSP 严格）
├── evidence/                  四份正式运行 + MANIFEST.json
├── tests/                     202 项 Python 测试 + JS 协议断言
├── bin/                       运行、录制、成片、封存脚本
├── docs/                      架构、声明边界、证据说明、工程记录
│   └── development/           开发过程的 plan / spec 存档
├── CONTEXT.md                 术语表与关键决议
└── requirements-presentation.txt
```

## 边界声明

本项目**区分三类结论**，全部记录在 [`docs/claims.md`](docs/claims.md)（声明—证据矩阵）：

- ✅ **已复验** —— 可由本仓库随附证据复算；
- 🟡 **演示级实现** —— 演示级不等于生产级；
- ❌ **未实现** —— 明确不冒充完成。

**可以证明**：九技能任务编排与严格审计；normal 完成 / recovery 自动恢复 / intervention 安全停车与人工介入；Isaac Sim 中以确定性运动目标驱动的可重复数字孪生；显式 USD 物理挂接与几何/关节双条件的载荷判定；扫掠碰撞认证；Fast-WAM 在官方任务上独立生成 7D 动作。

**不能证明**：

- 未接入任何真实叉车（无 SRC-5000、无实机控制）；
- 无 ROS 2 闭环、无真实 RGB-D/雷达感知、无安全 PLC；
- 控制方式为**确定性运动目标 + 显式物理挂接**的可重复演示降级，**不是标定力控**，也不是生产级动力学；
- **Fast-WAM 没有控制叉车**，未做叉车数据后训练；
- 论文报告的 190 ms 延迟**未在本机复现**，不得写成本项目实测；
- 当前结果不能用于生产安全认证。

异常由场景条件确定性注入，不是真实感知触发。

## 工程记录

本仓库的开发过程文档（设计取舍、失败与修正、每次升级的验收标准）保存在 [`docs/development/`](docs/development/)，[`docs/engineering-log.md`](docs/engineering-log.md) 是一份压缩后的时间线。其中记录了若干次重要的**推翻与重做**——例如最初版本的"真实执行"实为直接写 Xform 的动画、桥接曾经把九技能任务完整执行九次——这些失败与修正记录是本项目可信度的一部分。

---

## License

见 [LICENSE](LICENSE)。
