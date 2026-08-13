# 双层架构仓库演示视频实施计划

> **执行要求：** 按测试驱动方式逐项实施；每项完成后运行聚焦测试；全部完成后做端到端验收并发布到现有公开分支。

**目标：** 生成三套可追溯的 2560×1080 双栏工业演示视频，并在现有网页中优先播放，同时保持原始 Isaac Sim 证据完整。

**架构：** `events.jsonl` 经纯状态投影生成右侧决策摘要，Pillow 渲染信息层，FFmpeg 与原始 Isaac 视频合成。Isaac 场景可选引用 SimReady Warehouse-01 资产并提供程序化回退。API、网页和证据清单把原始片与演示片作为两个独立媒体工件处理。

**技术栈：** Python 3、Pillow、FFmpeg/FFprobe、USD/Isaac Sim 6.0.1、原生 HTML/CSS/JavaScript、unittest。

---

### 任务 1：可审计的双层状态投影

**文件：**
- 新建：`tests/test_presentation.py`
- 新建：`demo/seer_demo/presentation.py`

1. 先写正常、恢复、人员介入三个失败测试，验证同一时间点的大脑目标、技能分发、小脑状态、安全门控和最近审计事件。
2. 实现事件读取、时间点选择和 `decision_snapshot` 纯函数。
3. 保证输出只有结构化决策摘要，没有隐藏思维链字段或不可验证文本。
4. 运行：`python3 -m unittest tests.test_presentation -v`。

### 任务 2：双栏画面渲染与视频合成

**文件：**
- 修改：`tests/test_presentation.py`
- 修改：`demo/seer_demo/presentation.py`
- 新建：`scripts/build_split_presentation.py`

1. 先写分辨率、帧/时间映射、媒体元数据和命令构造测试。
2. 实现 2560×1080 工业面板、中文字体回退、状态色和最近事件时间线。
3. 实现逐帧 PNG 临时层与 FFmpeg 合成；始终保留 `simulation.mp4`。
4. 使用小型视频做真实渲染/FFprobe 冒烟测试，确认输出像素、帧率和时长。

### 任务 3：证据模型、服务和网页播放

**文件：**
- 修改：`tests/test_manifest.py`
- 修改：`tests/test_server.py`
- 修改：`tests/test_web_protocol.py`
- 修改：`demo/seer_demo/manifest.py`
- 修改：`demo/seer_demo/server.py`
- 修改：`demo/web/app.js`
- 修改：`demo/web/styles.css`

1. 先写演示片清单、媒体白名单、优先播放与回退测试。
2. 在摘要中加入演示片字段并在清单中分别校验两种媒体。
3. 服务端只开放摘要声明的媒体；网页优先演示片、缺失时回退原片。
4. 运行聚焦 Python/JavaScript 测试。

### 任务 4：扩大仓库并接入 SimReady 资产

**文件：**
- 修改：`tests/test_timeline.py`
- 修改：`tests/test_cli.py`
- 修改：`demo/seer_demo/isaac/scene.py`
- 修改：`demo/seer_demo/isaac/runner.py`
- 修改：`demo/seer_demo/cli.py`

1. 先写资产路径、程序化回退、场景范围和镜头阶段选择测试。
2. 扩大地面、墙体、货架通道和装卸区域；可选引用官方 Warehouse-01 资产。
3. 根据任务阶段选择仓内全景、取货近景和放置视角，且不改变物理执行时间轴。
4. 在远端 Isaac Sim 做单帧资产/镜头试渲染，失败时保留程序化回退并记录原因。

### 任务 5：正式重渲染三场景

**文件：**
- 替换：`demo/evidence/isaac-*/simulation.mp4`
- 替换：`demo/evidence/isaac-*/events.jsonl`
- 替换：`demo/evidence/isaac-*/scene.usda`
- 替换：`demo/evidence/isaac-*/summary.json`

1. 在远端 Isaac Sim 6.0.1 分别运行正常、抓取恢复、人员介入场景。
2. 校验终态、帧数、物理时间、事件连续性和场景文件。
3. 下载正式工件到本地，绝不手工改写运行日志。

### 任务 6：生成双栏成片并更新项目交付

**文件：**
- 新建：`demo/evidence/isaac-*/presentation.mp4`
- 修改：`demo/evidence/MANIFEST.json`
- 修改：`demo/evidence/README.md`
- 修改：`demo/README.md`
- 修改：`demo/CLAIMS.md`
- 修改：`demo/项目总结与交付说明.md`

1. 从每套正式日志生成演示片并用 FFprobe 校验。
2. 重建证据清单，确认原片和演示片哈希均可复验。
3. 更新运行说明、架构展示说明、企业演示话术和验证边界。
4. 运行全量 Python/JavaScript/清单/编译/脚本检查。
5. 在本地浏览器播放并截图检查；修复所有发现的问题。
6. 提交并推送到 `captainNemoCheng/seer-competition:feature/seer-hvla-demo`，更新现有 PR。

### 任务 7：补充 UsdPhysics 与显式物理附着

**文件：**
- 修改：`tests/test_timeline.py`
- 修改：`demo/seer_demo/isaac/scene.py`
- 修改：`demo/seer_demo/isaac/runner.py`

1. 先写物理规格、叉槽、附着状态和证据字段的失败测试。
2. 添加 PhysicsScene、碰撞、质量、kinematic rigid body、ArticulationRoot 和 FixedJoint。
3. 让 `observe_scene` 同时根据 joint 状态和几何关系确认附着。
4. 摘要明确记录 `kinematic_targets_with_explicit_physics_attachment` 降级模式。
5. 在 Isaac 6.0.1 做 smoke，随后重新录制三条正式证据。

### 任务 8：四 Tab AgentOS 演示页

**文件：**
- 修改：`tests/test_server.py`
- 修改：`tests/test_web_protocol.py`
- 修改：`tests/web_protocol_test.js`
- 修改：`demo/web/index.html`
- 修改：`demo/web/styles.css`
- 修改：`demo/web/protocol.js`
- 修改：`demo/web/app.js`

1. 先写四 Tab、当前时刻事件投影、Fast-WAM 边界和旧运行取消测试。
2. 加入成功/恢复/介入/Fast-WAM Tab。
3. 加入飞书风格任务发送、技能分发和事件驱动的指令/审计更新。
4. Fast-WAM 仅呈现独立验证与待补素材，不冒充叉车控制。
5. 做 JSC、HTTP 和浏览器点击/播放验证。
