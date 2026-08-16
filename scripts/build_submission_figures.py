#!/usr/bin/env python3
"""生成鹰之团参赛方案附图（非 AI 生成部分）。输出：参赛方案/figures。"""
from __future__ import annotations
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "参赛方案" / "figures"
FONT = "C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = "C:\Windows\Fonts\msyhbd.ttc"
BG = "#0A1622"; PANEL = "#102433"; PANEL2 = "#0C1921"; LINE = "#2B3D48"
INK = "#F2F7FA"; MUTED = "#9EB3C5"; CYAN = "#3ED1E6"; BLUE = "#4AA8FF"
AMBER = "#FFB547"; GREEN = "#43D17C"; RED = "#FF5D68"; DARK = "#07111D"
TEAM = "鹰之团"

def f(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)

def canvas(w, h):
    img = Image.new("RGB", (w, h), BG)
    return img, ImageDraw.Draw(img)

def rrect(d, box, radius, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def header(d, w, eyebrow, title, sub=""):
    d.text((60, 34), eyebrow, font=f(18, True), fill=CYAN)
    d.text((60, 64), title, font=f(42, True), fill=INK)
    if sub:
        d.text((60, 122), sub, font=f(21), fill=MUTED)

def center_text(d, cx, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text((cx - w / 2, y), text, font=font, fill=fill)

def wrap(d, text, font, max_width):
    lines = []
    for raw in text.split("\n"):
        if not raw:
            lines.append(""); continue
        cur = ""
        for ch in raw:
            if d.textlength(cur + ch, font=font) <= max_width:
                cur += ch
            else:
                if cur: lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines

def draw_lines(d, xy, lines, font, fill, line_gap=8):
    x, y = xy
    for line in lines:
        d.text((x, y), line, font=font, fill=fill)
        y += font.size + line_gap
    return y

def arrow(d, p0, p1, color, width=5):
    d.line([p0, p1], fill=color, width=width)
    x0, y0 = p1; x1, y1 = p0
    ang = math.atan2(y0 - y1, x0 - x1)
    L = 16
    a = ang + math.radians(22); b = ang - math.radians(22)
    d.polygon([p1, (x0 - L * math.cos(a), y0 - L * math.sin(a)), (x0 - L * math.cos(b), y0 - L * math.sin(b))], fill=color)

def badge(d, x, y, text, color):
    font = f(17, True); pad = 14
    w = int(d.textlength(text, font=font)) + pad * 2
    rrect(d, (x, y, x + w, y + 38), 19, fill=color)
    d.text((x + pad, y + 8), text, font=font, fill=DARK)
    return x + w + 16

def save(img, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    img.save(path, optimize=True)
    print("saved", path.name, img.size)

# ---------------------------------------------------------------- 图 C：四层架构
def fig_c():
    W, H = 1680, 1320
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 方案附图 C", "四层架构总览：自然语言 → 任务图 → 技能序列 → 物理执行",
           "每层有明确平台、输入输出与验证证据；层间接口可独立测试，故障可定位到具体层")
    layers = [
        {"id": "01", "name": "交互理解层", "color": BLUE, "sub": "自然语言 → 结构化任务图",
         "modules": ["自然语言任务解析", "时效 / 优先级 / 位置解析", "多模态上下文理解"],
         "notes": ["平台：飞书 Aily", "节奏：慢推理级（约 1–5 s）", "输出：结构化任务图"], "tag": "已运行"},
        {"id": "02", "name": "AgentOS 编排层", "color": CYAN, "sub": "任务图 → 技能序列 + 监控恢复",
         "modules": ["任务分解 + 技能库（9 技能）", "状态记忆 / Scene Graph", "Fallback 策略库"],
         "notes": ["平台：Aily + 多维表格 ×5", "机制：单实例桥接 + 排他锁", "产物：技能序列 / 审计 / 告警"], "tag": "已运行"},
        {"id": "03", "name": "VLA / 执行层", "color": AMBER, "sub": "技能 + 观测 → 目标参数 → 动作验证",
         "modules": ["Fast-WAM / VLA 策略", "输出：技能选择 + 目标参数", "生成 → 验证 → 执行流水线"],
         "notes": ["验证：官方 LIBERO task 8", "Fast-WAM 5/5（限定固定初态）", "控制 20 Hz · 300 步预算"], "tag": "部分实测"},
        {"id": "04", "name": "M4 / 规控与安全层", "color": GREEN, "sub": "目标参数 → 物理执行 + 安全停车",
         "modules": ["Skill Policy + 安全停车", "OBB / SAT 扫掠守卫 V4", "USD FixedJoint + M4 调度"],
         "notes": ["平台：Isaac Sim 6.0.1 / OpenUSD", "录像 1280×720 · 8 fps · JSONL 事件", "V4：禁碰 / 穿透 / 接触违规 = 0"], "tag": "仿真已验证"},
    ]
    y = 180; band_h = 238; gap = 34
    left_x, left_w = 80, 1120; note_x, note_w = 1230, 380
    centers = []
    for layer in layers:
        color = layer["color"]
        rrect(d, (left_x, y, left_x + left_w, y + band_h), 18, fill=PANEL, outline=color, width=2)
        d.ellipse((left_x + 24, y + 24, left_x + 92, y + 92), fill=color)
        center_text(d, left_x + 58, y + 38, layer["id"], f(26, True), DARK)
        d.text((left_x + 112, y + 20), layer["name"], font=f(30, True), fill=INK)
        badge(d, left_x + 112, y + 64, layer["tag"], color)
        d.text((left_x + 112, y + 112), layer["sub"], font=f(19), fill=MUTED)
        mods = layer["modules"]; cols = 2 if len(mods) == 4 else 3; rows = 2 if len(mods) == 4 else 1
        mx = left_x + 30; mw = int((left_w - 60 - (cols - 1) * 16) / cols); mh = 56; my = y + 158
        for i, text in enumerate(mods):
            r, c = divmod(i, cols)
            bx = mx + c * (mw + 16); by = my + r * (mh + 10)
            rrect(d, (bx, by, bx + mw, by + mh), 10, fill=PANEL2, outline=LINE)
            center_text(d, bx + mw // 2, by + 18, text, f(18, True), INK)
        rrect(d, (note_x, y, note_x + note_w, y + band_h), 18, fill=DARK, outline=LINE)
        d.text((note_x + 24, y + 18), "平台与证据", font=f(20, True), fill=CYAN)
        yy = y + 58
        for note in layer["notes"]:
            d.ellipse((note_x + 26, yy + 8, note_x + 34, yy + 16), fill=color)
            yy = draw_lines(d, (note_x + 48, yy), wrap(d, note, f(17), note_w - 80), f(17), INK, 7)
        centers.append((y + band_h // 2, color))
        y += band_h + gap
    for i in range(3):
        arrow(d, (left_x + 240, centers[i][0] + 60), (left_x + 240, centers[i + 1][0] - 60), centers[i + 1][1], 6)
    by = y - 16
    rrect(d, (80, by, W - 80, by + 86), 16, fill=PANEL, outline=CYAN, width=2)
    d.text((110, by + 12), "同一条事实链", font=f(20, True), fill=CYAN)
    draw_lines(d, (110, by + 44), wrap(d, "四个场景的技能、Fallback、终态、时长全部由同一 events.jsonl 契约派生；网页只读回放，不展示隐藏思维过程", f(18), W - 300), f(18), INK, 6)
    save(img, "fig-C-四层架构总览.png")

# ---------------------------------------------------------------- 图 D：技能链 + Fallback
def fig_d():
    W, H = 1900, 1220
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 方案附图 D", "九技能执行链 × Fallback 状态机",
           "normal 全绿完成；recovery 经 FB-F01 修正后完成；intervention 安全停车并请求人工（真实事件与录像同源）")
    skills = [
        ("进箱导航", "FORK-NAV-01"), ("精确对位", "FORK-NAV-03"), ("栈板识别", "FORK-PER-01"),
        ("货叉插入", "FORK-OP-01"), ("门架起升", "FORK-OP-02"), ("货叉倾斜", "FORK-OP-03"),
        ("月台区导航", "FORK-NAV-02"), ("传送带对接", "FORK-OP-05"), ("栈板放置", "FORK-OP-04"),
    ]
    gw, gh = 320, 88
    gx0, gy0, gxgap, gygap = 90, 185, 30, 18
    centers = []
    for i, (name, code) in enumerate(skills):
        r, c = divmod(i, 3)
        x = gx0 + c * (gw + gxgap); y = gy0 + r * (gh + gygap)
        rrect(d, (x, y, x + gw, y + gh), 12, fill=PANEL, outline=BLUE)
        center_text(d, x + gw // 2, y + 14, name, f(22, True), INK)
        center_text(d, x + gw // 2, y + 48, code, f(15, True), MUTED)
        centers.append((x + gw // 2, y + gh // 2))
        if i < 8:
            nx = gx0 + ((i + 1) % 3) * (gw + gxgap); ny = gy0 + ((i + 1) // 3) * (gh + gygap)
            if (i + 1) % 3 == 0:
                arrow(d, (x + gw // 2, y + gh), (x + gw // 2, ny), BLUE, 4)
            else:
                arrow(d, (x + gw, y + gh // 2), (nx, y + gh // 2), BLUE, 4)
    px = gx0 + 2 * (gw + gxgap) + gw + 95; py = gy0 + 2 * (gh + gygap) + 22
    rrect(d, (px, py, px + 250, py + 62), 31, fill=GREEN)
    center_text(d, px + 125, py + 8, "COMPLETED · 9/9", f(21, True), DARK)
    center_text(d, px + 125, py + 34, "实测 66.25 s", f(16, True), DARK)
    arrow(d, (gx0 + 2 * (gw + gxgap) + gw, centers[8][1]), (px, centers[8][1]), GREEN, 5)
    ry = gy0 + 3 * (gh + gygap) + 30
    d.text((90, ry - 4), "RECOVERY · 自动恢复", font=f(19, True), fill=AMBER)
    bx = 90
    rtexts = [("首次对位失败", "栈板横向偏移超限"), ("FB-F01 横向修正", "重新识别与对位后重试")]
    rc = []
    for t1, t2 in rtexts:
        bw, bh = 430, 66
        rrect(d, (bx, ry, bx + bw, ry + bh), 12, fill=PANEL, outline=AMBER, width=2)
        center_text(d, bx + bw // 2, ry + 12, t1, f(20, True), INK)
        center_text(d, bx + bw // 2, ry + 38, t2, f(16), MUTED)
        rc.append((bx + bw, ry + bh // 2)); bx += bw + 70
    arrow(d, rc[0], rc[1], AMBER, 4)
    arrow(d, (rc[1][0], rc[1][1]), (centers[1][0], centers[1][1] - 44), AMBER, 4)
    rx = bx + 50
    rrect(d, (rx, ry - 6, rx + 250, ry + 56), 31, fill=GREEN)
    center_text(d, rx + 125, ry + 1, "COMPLETED · 9/9", f(21, True), DARK)
    center_text(d, rx + 125, ry + 27, "实测 77.25 s", f(16, True), DARK)
    arrow(d, (rx - 75, ry + 25), (rx, ry + 25), GREEN, 5)
    iy = ry + 160
    d.text((90, iy - 8), "INTERVENTION · 安全介入", font=f(19, True), fill=RED)
    bx = 90
    iboxes = [("连续三次识别失败", "遮挡场景注入"), ("FB-F02 切换观察位姿", "两个不同视角再试"), ("FB-F07 箱外安全停车", "速度 |v| ≤ 0.01 m/s")]
    ic = []
    for t1, t2 in iboxes:
        bw, bh = 430, 62
        rrect(d, (bx, iy, bx + bw, iy + bh), 12, fill=PANEL, outline=(RED if "FB-F07" in t1 or "失败" in t1 else AMBER), width=2)
        center_text(d, bx + bw // 2, iy + 12, t1, f(18, True), INK)
        center_text(d, bx + bw // 2, iy + 36, t2, f(15), MUTED)
        ic.append((bx + bw, iy + bh // 2)); bx += bw + 50
    for a, b in zip(ic, ic[1:]):
        arrow(d, a, b, AMBER, 4)
    rx = bx + 30
    rrect(d, (rx, iy - 12, rx + 290, iy + 74), 31, fill=RED)
    center_text(d, rx + 145, iy + 2, "HUMAN_REQUIRED", f(22, True), DARK)
    center_text(d, rx + 145, iy + 30, "等待人工介入 · 36.0 s", f(16, True), DARK)
    arrow(d, (rx - 80, iy + 31), (rx, iy + 31), RED, 5)
    fy = iy + 150
    rrect(d, (90, fy, W - 90, fy + 72), 14, fill=DARK, outline=LINE)
    draw_lines(d, (120, fy + 14), wrap(d, "颜色即终态语义（与线上 Demo 一致）：蓝=运行 · 琥珀=Fallback/恢复 · 绿=完成 · 红=人工介入。三场景均来自正式 Isaac 录像与连续事件链。", f(17), W - 240), f(17), INK, 6)
    save(img, "fig-D-九技能链与Fallback状态机.png")

# ---------------------------------------------------------------- 图 F：单一事实源证据链
def fig_f():
    W, H = 1680, 900
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 方案附图 F", "单一事实源证据链：从飞书任务到只读证据控制台",
           "任务只启动一次 runner；页面所有数字必须由 events.jsonl 推导，不能伪造执行结果")
    nodes = [
        ("Aily / 飞书任务", "自然语言任务\n乐观认领", BLUE),
        ("单实例桥接", "排他锁\n只启动一次 runner", CYAN),
        ("Isaac Sim 6.0.1", "实际执行\n物理观测写入", AMBER),
        ("events.jsonl", "唯一事实源\n严格语义校验", GREEN),
        ("Manifest 封存", "SHA-256\n视频 / 场景清单", CYAN),
        ("网页 / 审计回写", "只读回放\n输入不符 fail-closed", GREEN),
    ]
    n = len(nodes); bw = 225; gap = 32
    total = n * bw + (n - 1) * gap
    x0 = (W - total) // 2; y0 = 245; bh = 190
    for i, (title, sub, color) in enumerate(nodes):
        x = x0 + i * (bw + gap)
        rrect(d, (x, y0, x + bw, y0 + bh), 16, fill=PANEL, outline=color, width=3)
        center_text(d, x + bw // 2, y0 + 16, title, f(19, True), INK)
        lines = wrap(d, sub, f(16), bw - 30); ty = y0 + 62
        for line in lines:
            center_text(d, x + bw // 2, ty, line, f(16), MUTED); ty += 26
        center_text(d, x + bw // 2, y0 + bh - 40, f"{i+1:02d}", f(24, True), color)
        if i < n - 1:
            arrow(d, (x + bw + 4, y0 + bh // 2), (x + bw + gap - 6, y0 + bh // 2), CYAN, 5)
    badges = [("现场任务 T-DEMO-20260813-001", GREEN), ("审计事件 0–19 连续", GREEN), ("201 项 Python + 50 项 JS 断言", CYAN)]
    bx = x0; by = y0 + bh + 56
    for text, color in badges:
        font = f(17, True); pad = 16
        w = int(d.textlength(text, font=font)) + pad * 2
        rrect(d, (bx, by, bx + w, by + 44), 22, fill=color)
        d.text((bx + pad, by + 11), text, font=font, fill=DARK)
        bx += w + 22
    fy = by + 92
    rrect(d, (x0, fy, W - x0, fy + 128), 16, fill=DARK, outline=LINE)
    d.text((x0 + 24, fy + 14), "四份正式证据（线上可点开验证）", font=f(19, True), fill=CYAN)
    runs = [("normal", "COMPLETED · 66.25 s", GREEN), ("recovery", "COMPLETED · 77.25 s", GREEN),
            ("intervention", "HUMAN_REQUIRED · 36.0 s", RED), ("Fast-WAM", "官方 task 8 · 5/5 固定初态", GREEN)]
    rx = x0 + 24
    for name, desc, color in runs:
        rrect(d, (rx, fy + 58, rx + 345, fy + 110), 12, fill=PANEL2, outline=color, width=2)
        d.text((rx + 18, fy + 68), name, font=f(19, True), fill=INK)
        d.text((rx + 18, fy + 92), desc, font=f(15), fill=MUTED)
        rx += 361
    save(img, "fig-F-单一事实源证据链.png")

# ---------------------------------------------------------------- 图 H：量化对比
def fig_h():
    W, H = 1500, 1060
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 方案附图 H", "方案价值量化对比",
           "灰色 = 行业参考 / 传统方案；青色 = 本方案设计目标（需在目标产线实测验证）")
    rows = [
        ("故障定位时间", "数十小时", 780, "≤ 数小时", 150),
        ("新工序切换时间", "数天–数周", 750, "小时级", 120),
        ("单台效率 vs 人工", "30–50%", 360, "60–80%", 560),
        ("多机协同产线提升", "传统逐台调度", 120, "30%+", 260),
    ]
    y = 215; label_x = 90; bar_x = 430; max_w = 720
    for name, cur_txt, cur_w, tgt_txt, tgt_w in rows:
        d.text((label_x, y + 4), name, font=f(22, True), fill=INK)
        rrect(d, (bar_x, y, bar_x + max_w, y + 56), 10, fill=PANEL2, outline=LINE)
        rrect(d, (bar_x, y, bar_x + cur_w, y + 56), 10, fill="#5A6B78")
        d.text((bar_x + 12, y + 15), cur_txt, font=f(18, True), fill=INK)
        ty = y + 76
        rrect(d, (bar_x, ty, bar_x + max_w, ty + 56), 10, fill=PANEL2, outline=LINE)
        rrect(d, (bar_x, ty, bar_x + tgt_w, ty + 56), 10, fill=CYAN)
        d.text((bar_x + 12, ty + 15), tgt_txt, font=f(18, True), fill=DARK)
        y += 166
    fy = y + 18
    rrect(d, (90, fy, W - 90, fy + 150), 16, fill=PANEL, outline=GREEN, width=2)
    d.text((120, fy + 14), "已经过仿真实测 / 可复验的数字（不属上述目标值）", font=f(19, True), fill=GREEN)
    measured = ["normal：66.25 s · 20 事件 · COMPLETED", "recovery：77.25 s · 24 事件 · FB-F01 后完成",
                "intervention：36.0 s · 18 事件 · HUMAN_REQUIRED", "Fast-WAM：官方 task 8 · 固定初态 5/5（77–84 步）"]
    for i, text in enumerate(measured):
        x = 120 + (i % 2) * 660; yy = fy + 58 + (i // 2) * 34
        d.ellipse((x, yy + 7, x + 12, yy + 19), fill=GREEN)
        d.text((x + 22, yy), text, font=f(16), fill=INK)
    save(img, "fig-H-方案价值量化对比.png")

# ---------------------------------------------------------------- 图 K：技术栈映射
def fig_k():
    W, H = 1680, 1120
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 方案附图 K", "仙工技术栈 × 本方案模块的落位映射",
           "依据官网公开资料的设计映射；当前阶段为仿真原型，尚未接入 SRC-5000 实机")
    lx, ly, lw, lh = 80, 195, 430, 620
    rrect(d, (lx, ly, lx + lw, ly + lh), 18, fill=PANEL, outline=BLUE, width=2)
    center_text(d, lx + lw // 2, ly + 18, "仙工智能平台（公开资料）", f(22, True), INK)
    left_items = [
        ("SRC-5000", ["156 TOPS AI 算力", "RTOS + TSN 实时核", "WBC / SLAM / 通信中间件"]),
        ("M4 调度系统", ["多机任务调度", "百万级库位 / 十万级点位", "动态派单与路径优化"]),
        ("星云平台", ["1000+ 机器人型号生态", "机型 / 应用管理", "可配置机器人本体与技能"]),
    ]
    yy = ly + 70
    for title, lines in left_items:
        rrect(d, (lx + 24, yy, lx + lw - 24, yy + 150), 12, fill=PANEL2, outline=LINE)
        d.text((lx + 44, yy + 16), title, font=f(20, True), fill=BLUE)
        ty = yy + 54
        for line in lines:
            d.ellipse((lx + 48, ty + 7, lx + 56, ty + 15), fill=BLUE)
            d.text((lx + 68, ty), line, font=f(16), fill=INK)
            ty += 30
        yy += 166
    mx, mw = 570, 470
    rrect(d, (mx, ly, mx + mw, ly + lh), 18, fill=PANEL, outline=CYAN, width=2)
    center_text(d, mx + mw // 2, ly + 18, "本方案模块落位（设计映射）", f(22, True), INK)
    mid_items = [
        ("Aily + AgentOS 编排", "任务分解 / 技能库 / Fallback / 审计", CYAN),
        ("VLA / Fast-WAM 推理", "输出技能参数；SRC-5000 AI 算力承载", AMBER),
        ("Skill Policy + 安全门控", "规控轨迹 + OBB/SAT 守卫；RTOS 实时核", GREEN),
        ("多机协同", "M4 调度 AgentOS 实例与全局资源", BLUE),
        ("技能包 / 构型适配", "星云平台选配技能子集，跨构型复用", CYAN),
    ]
    yy = ly + 72
    for title, sub, color in mid_items:
        hh = 96
        rrect(d, (mx + 24, yy, mx + mw - 24, yy + hh), 12, fill=PANEL2, outline=color, width=2)
        d.text((mx + 44, yy + 12), title, font=f(19, True), fill=color)
        draw_lines(d, (mx + 44, yy + 44), wrap(d, sub, f(15), mw - 90), f(15), MUTED, 5)
        yy += hh + 14
    rx, rw = 1090, 500
    rrect(d, (rx, ly, rx + rw, ly + lh), 18, fill=PANEL, outline=GREEN, width=2)
    center_text(d, rx + rw // 2, ly + 18, "当前已验证证据", f(22, True), INK)
    right_items = [
        ("Isaac Sim 6.0.1 三场景", "normal / recovery / intervention 正式录像", GREEN),
        ("Fast-WAM 官方 task 8", "固定初态 5/5，7D 动作全来自 checkpoint", GREEN),
        ("证据链", "events.jsonl + Manifest SHA-256 + 网页控制台", CYAN),
        ("实机边界", "尚未接入 SRC-5000 / 真车 / 安全 PLC", RED),
    ]
    yy = ly + 72
    for title, sub, color in right_items:
        hh = 104
        rrect(d, (rx + 24, yy, rx + rw - 24, yy + hh), 12, fill=PANEL2, outline=color, width=2)
        d.text((rx + 44, yy + 14), title, font=f(19, True), fill=color)
        draw_lines(d, (rx + 44, yy + 48), wrap(d, sub, f(15), rw - 90), f(15), MUTED, 6)
        yy += hh + 16
    by = ly + lh + 34
    rrect(d, (80, by, W - 80, by + 70), 14, fill=DARK, outline=AMBER, width=2)
    draw_lines(d, (110, by + 12), wrap(d, "下一阶段输入：真实叉车 USD/URDF、底盘/门架/货叉接口与频率、急停与安全 PLC 协议、脱敏训练数据。以上均在方案设计层等待企业对接。", f(17), W - 240), f(17), INK, 6)
    save(img, "fig-K-仙工技术栈映射.png")

# ---------------------------------------------------------------- 图 L：路线图
def fig_l():
    W, H = 1680, 960
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 方案附图 L", "影子模式三阶段落地路线图",
           "先规控跑通、再让 VLA/WAM 影子学习、最后端侧接管；每阶段都有退出条件")
    phases = [
        ("阶段 1 · 0–3 月", BLUE, "规控跑通 + WAM 影子建议",
         ["Transformer + 规控先跑通产线", "Fast-WAM 只走“建议通道”，不控车", "同一事件链记录建议 vs 实际动作", "九技能 / 三工况闭环演示"],
         "退出条件：9 技能闭环 + 事件审计可复验"),
        ("阶段 2 · 3–6 月", AMBER, "数据积累 + 有条件接管",
         ["采集脱敏叉车图像 / 状态 / 操作数据", "WAM/VLA 基模微调，缩小叉车动作分布", "影子模式：离线回放对比 + 安全门控", "人工确认后，在受限场景有限接管"],
         "退出条件：影子对比达标 + 安全门控通过"),
        ("阶段 3 · 6–12 月", GREEN, "端侧部署 + 多构型推广",
         ["端侧算力升级至 1000–2000 TOPS", "SRC-5000 承载推理 + 实时规控", "多机协同接入 M4 / 星云平台", "技能包跨行业、跨构型复用"],
         "退出条件：连续运行验收 + 标准符合性检查"),
    ]
    x0, y0 = 80, 200; cw, ch, gap = 486, 560, 30
    for i, (title, color, sub, bullets, exit_crit) in enumerate(phases):
        x = x0 + i * (cw + gap)
        rrect(d, (x, y0, x + cw, y0 + ch), 18, fill=PANEL, outline=color, width=3)
        rrect(d, (x + 24, y0 + 20, x + cw - 24, y0 + 88), 12, fill=color)
        center_text(d, x + cw // 2, y0 + 34, title, f(22, True), DARK)
        center_text(d, x + cw // 2, y0 + 60, sub, f(16, True), DARK)
        yy = y0 + 126
        for bullet in bullets:
            d.ellipse((x + 40, yy + 8, x + 48, yy + 16), fill=color)
            yy = draw_lines(d, (x + 62, yy), wrap(d, bullet, f(17), cw - 100), f(17), INK, 6)
            yy += 12
        rrect(d, (x + 24, y0 + ch - 88, x + cw - 24, y0 + ch - 26), 12, fill=PANEL2, outline=color)
        draw_lines(d, (x + 42, y0 + ch - 72), wrap(d, exit_crit, f(15), cw - 80), f(15), color, 5)
        if i < 2:
            arrow(d, (x + cw + 2, y0 + ch // 2), (x + cw + gap - 4, y0 + ch // 2), color, 7)
    by = y0 + ch + 40
    rrect(d, (80, by, W - 80, by + 72), 14, fill=DARK, outline=LINE)
    draw_lines(d, (110, by + 13), wrap(d, "当前完成：阶段 1 的仿真侧闭环（Isaac 三场景 + Fast-WAM 官方任务实测 + 证据链）。实机时间点与算力演进为规划目标，依赖企业数据与接口到位。", f(17), W - 240), f(17), INK, 6)
    save(img, "fig-L-影子模式三阶段路线图.png")

# ---------------------------------------------------------------- 图 M：竞品定位
def fig_m():
    W, H = 1450, 1160
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 方案附图 M", "技术路线定位：在“泛化”与“可控”之间取工业可用平衡",
           "横轴 = 可控性 / 可审计性；纵轴 = 泛化能力 / 场景柔性（定性示意，非实测分数）")
    margin_l, margin_r, margin_t, margin_b = 200, 120, 250, 200
    ax0 = margin_l; ay0 = H - margin_b; ax1 = W - margin_r; ay1 = margin_t
    d.rectangle((ax0, ay1, ax1, ay0), outline=LINE, width=3)
    for i in range(1, 5):
        x = ax0 + (ax1 - ax0) * i / 5; y = ay0 - (ay0 - ay1) * i / 5
        d.line((x, ay0, x, ay1), fill="#143043", width=1)
        d.line((ax0, y, ax1, y), fill="#143043", width=1)
    zx0 = ax0 + (ax1 - ax0) * 0.48; zy0 = ay0 - (ay0 - ay1) * 0.52
    zx1 = ax0 + (ax1 - ax0) * 0.88; zy1 = ay0 - (ay0 - ay1) * 0.90
    rrect(d, (zx0, zy1, zx1, zy0), 22, fill="#0E2A2E", outline=CYAN, width=3)
    d.text((zx0 + 18, zy0 + 16), "工业落地窗口", font=f(18, True), fill=CYAN)
    d.text((zx0 + 18, zy0 + 48), "泛化与可控的平衡区", font=f(15), fill=CYAN)
    points = [
        ("传统规则自动化", 0.88, 0.10, "#5A6B78", "规则可靠但难以泛化"),
        ("端到端 VLA", 0.10, 0.90, AMBER, "泛化强但过程难审计"),
        ("模块化 VLA", 0.58, 0.58, BLUE, "中间形态，接口仍在磨合"),
        ("多模态大模型 Agent", 0.46, 0.74, MUTED, "调度灵活但动作验证不足"),
        ("本方案：层次化 VLA + AgentOS", 0.72, 0.76, CYAN, "VLA 只出技能参数，验证层兜底"),
    ]
    for name, px, py, color, note in points:
        x = ax0 + (ax1 - ax0) * px; y = ay0 - (ay0 - ay1) * py
        if name.startswith("本方案"):
            r = 20
            d.ellipse((x - r, y - r, x + r, y + r), fill=color, outline="#E8FBFF", width=4)
            d.text((x - r + 3, y - r + 4), "★", font=f(24, True), fill=DARK)
            d.text((x - 150, y - 78), name, font=f(20, True), fill=CYAN)
            d.text((x - 150, y - 46), note, font=f(15), fill=INK)
        else:
            r = 13
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)
            d.text((x + 18, y - 30), name, font=f(18, True), fill=INK)
            d.text((x + 18, y - 4), note, font=f(14), fill=MUTED)
    center_text(d, (ax0 + ax1) // 2, ay0 + 30, "可控性 / 可审计性 →", f(20, True), INK)
    yl = ay1 + (ay0 - ay1) // 2 - 10
    d.text((60, yl - 70), "泛", font=f(24, True), fill=INK)
    d.text((60, yl - 30), "化", font=f(24, True), fill=INK)
    d.text((60, yl + 10), "柔", font=f(24, True), fill=INK)
    d.text((60, yl + 50), "性", font=f(24, True), fill=INK)
    d.text((62, yl + 96), "↑", font=f(20, True), fill=MUTED)
    fy = ay0 + 70
    rrect(d, (200, fy, W - 140, fy + 62), 14, fill=DARK, outline=CYAN, width=2)
    draw_lines(d, (230, fy + 10), wrap(d, "本方案的关键差异：VLA 输出“技能选择 + 目标参数”而非关节角度，执行前经过运动学 → 碰撞 → 人机安全三层验证，任何不通过都触发 Fallback。", f(16), W - 380), f(16), INK, 5)
    save(img, "fig-M-技术路线定位图.png")

# ---------------------------------------------------------------- 图 N：场景迭代对比
def fig_n():
    sources = [
        ("shots_v1_0.png", "V1 初版场景", "比例 / 朝向问题暴露"),
        ("shots_v3_top.png", "V3 俯视终审", "布局与机位验收"),
        ("shots_v4_final1.png", "V4 正式场景", "SimReady 资产 + 物理化"),
    ]
    thumbs = []
    tw, th = 760, 427
    for path, _, _ in sources:
        im = Image.open(ROOT / path).convert("RGB").resize((tw, th), Image.LANCZOS)
        thumbs.append(im)
    W = 2 * 60 + 3 * tw + 2 * 28
    H = 190 + th + 110
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 方案附图 N", "场景迭代：从能跑到不穿模、不遮挡、可验证", "三张均为项目真实 Isaac Sim 截图；每轮升级都有自动化测试与视觉抽帧复核")
    x = 60; y = 190
    for im, (_, title, sub) in zip(thumbs, sources):
        img.paste(im, (x, y))
        rrect(d, (x - 2, y - 2, x + tw + 2, y + th + 2), 6, outline=LINE, width=2)
        center_text(d, x + tw // 2, y + th + 22, title, f(21, True), INK)
        center_text(d, x + tw // 2, y + th + 58, sub, f(16), MUTED)
        x += tw + 28
    save(img, "fig-N-场景迭代对比.png")

# ---------------------------------------------------------------- 图 J：二维码
def fig_j():
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=16, border=2)
    qr.add_data("https://demo.aplearn.xyz/")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0A1622", back_color="#F2F7FA").convert("RGB")
    W, H = 1200, 1450
    img, d = canvas(W, H)
    header(d, W, "鹰之团 · 体验入口", "扫码直接体验（无需账号）", "公网地址：https://demo.aplearn.xyz/")
    size = 900
    x = (W - size) // 2; y = 250
    rrect(d, (x - 30, y - 30, x + size + 30, y + size + 30), 24, fill="#F2F7FA")
    img.paste(qr_img.resize((size, size), Image.LANCZOS), (x, y))
    center_text(d, W // 2, y + size + 40, "扫描二维码或浏览器打开上方地址", f(24, True), INK)
    steps = [
        "1. 打开页面后选择“正常卸货 / 自动恢复 / 安全介入 / Fast-WAM 碗→盘”",
        "2. 点击发送任务，页面才展开对应录像与审计证据",
        "3. 建议用深色演示模式投屏观看；视频时间轴可点击跳转",
    ]
    draw_lines(d, (120, y + size + 100), steps, f(20), INK, 16)
    fy = y + size + 240
    rrect(d, (120, fy, W - 120, fy + 92), 16, fill=PANEL, outline=CYAN, width=2)
    draw_lines(d, (150, fy + 14), wrap(d, "入口为只读证据控制台：所有数字由正式运行 events.jsonl 推导，不展示未经验证的结果。", f(18), W - 300), f(18), INK, 6)
    save(img, "fig-J-体验二维码.png")

def main():
    fig_c(); fig_d(); fig_f(); fig_h(); fig_k(); fig_l(); fig_m(); fig_n(); fig_j()
    print("done")

if __name__ == "__main__":
    main()
