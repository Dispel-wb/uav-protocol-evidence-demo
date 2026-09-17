"""Generate editable academic-style SVG diagrams for the project proposal.

The visual language follows the supplied Tianjin University application:
white canvas, restrained pastel regions, thin dark borders, dashed grouping,
blue directional arrows, and red emphasis for key problems.
"""

from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parent

COLORS = {
    "navy": "#244A7C",
    "blue": "#DCE8F8",
    "blue2": "#EEF4FB",
    "green": "#E5F2D6",
    "green_stroke": "#6B8E3F",
    "orange": "#FCE4D6",
    "orange_stroke": "#C87931",
    "purple": "#E9E1F5",
    "purple_stroke": "#7D5AA6",
    "yellow": "#FFF2CC",
    "red": "#C00000",
    "rose": "#F8D7DA",
    "gray": "#F2F2F2",
    "dark": "#273142",
    "muted": "#667085",
    "line": "#516B91",
}


def svg_open(w, h, title, subtitle=""):
    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
<defs>
  <marker id="arrow" markerWidth="11" markerHeight="8" refX="10" refY="4" orient="auto"><path d="M0,0 L11,4 L0,8 z" fill="{COLORS['line']}"/></marker>
  <marker id="arrow-red" markerWidth="11" markerHeight="8" refX="10" refY="4" orient="auto"><path d="M0,0 L11,4 L0,8 z" fill="{COLORS['red']}"/></marker>
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#263648" flood-opacity="0.16"/></filter>
  <style>
    text {{ font-family: 'Microsoft YaHei','Noto Sans SC','PingFang SC',Arial,sans-serif; fill:{COLORS['dark']}; }}
    .title {{ font-size:28px; font-weight:700; fill:{COLORS['navy']}; }}
    .subtitle {{ font-size:14px; fill:{COLORS['muted']}; }}
    .head {{ font-size:18px; font-weight:700; }}
    .label {{ font-size:15px; font-weight:700; }}
    .body {{ font-size:13px; }}
    .small {{ font-size:12px; fill:{COLORS['muted']}; }}
  </style>
</defs>
<rect x="0" y="0" width="{w}" height="{h}" fill="#FFFFFF"/>
<rect x="24" y="22" width="7" height="48" rx="3" fill="{COLORS['navy']}"/>
<text x="48" y="51" class="title">{escape(title)}</text>
<text x="48" y="74" class="subtitle">{escape(subtitle)}</text>
<line x1="38" y1="91" x2="{w-38}" y2="91" stroke="#B9C5D4" stroke-width="1"/>
'''


def svg_close():
    return "</svg>\n"


def t(x, y, lines, cls="body", anchor="middle", line_h=21, color=None, weight=None):
    if isinstance(lines, str):
        lines = [lines]
    attrs = f'class="{cls}" text-anchor="{anchor}"'
    if color:
        attrs += f' fill="{color}"'
    if weight:
        attrs += f' font-weight="{weight}"'
    spans = "".join(f'<tspan x="{x}" dy="{0 if i == 0 else line_h}">{escape(line)}</tspan>' for i, line in enumerate(lines))
    return f'<text x="{x}" y="{y}" {attrs}>{spans}</text>\n'


def box(x, y, w, h, title, body=(), fill=None, stroke=None, accent=None, dashed=False, radius=8):
    fill = fill or COLORS["blue2"]
    stroke = stroke or COLORS["navy"]
    dash = ' stroke-dasharray="8 5"' if dashed else ""
    s = f'<g filter="url(#shadow)"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{dash}/>'
    if accent:
        s += f'<rect x="{x}" y="{y}" width="8" height="{h}" rx="{radius}" fill="{accent}"/>'
    s += '</g>\n'
    s += t(x + w/2, y + 30, title, "label")
    if body:
        s += t(x + w/2, y + 58, list(body), "body", line_h=20)
    return s


def group(x, y, w, h, label, color=None):
    color = color or COLORS["navy"]
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="none" stroke="{color}" stroke-width="1.5" stroke-dasharray="10 6"/>'
            + t(x + 16, y + 22, label, "label", "start", color=color))


def arrow(x1, y1, x2, y2, label="", red=False, dashed=False):
    color = COLORS["red"] if red else COLORS["line"]
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    s = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.4" marker-end="url(#{"arrow-red" if red else "arrow"})"{dash}/>'
    if label:
        s += t((x1+x2)/2, (y1+y2)/2-8, label, "small", color=color)
    return s


def path_arrow(points, label="", red=False, dashed=False):
    color = COLORS["red"] if red else COLORS["line"]
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    pts = " ".join(f"{x},{y}" for x, y in points)
    s = f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.4" marker-end="url(#{"arrow-red" if red else "arrow"})"{dash}/>'
    if label:
        x, y = points[len(points)//2]
        s += t(x+8, y-8, label, "small", "start", color=color)
    return s


def decision(cx, cy, w, h, title):
    pts = f"{cx},{cy-h/2} {cx+w/2},{cy} {cx},{cy+h/2} {cx-w/2},{cy}"
    return f'<polygon points="{pts}" fill="{COLORS["yellow"]}" stroke="{COLORS["orange_stroke"]}" stroke-width="1.8" filter="url(#shadow)"/>' + t(cx, cy+5, title, "label")


def save(name, w, h, title, subtitle, content):
    (ROOT / f"{name}.svg").write_text(svg_open(w, h, title, subtitle) + content + svg_close(), encoding="utf-8")


def fig_2_1():
    w, h = 1600, 820
    s = t(220, 135, "现实痛点", "head", color=COLORS["green_stroke"])
    s += t(800, 135, "对应研究内容", "head", color=COLORS["orange_stroke"])
    s += t(1380, 135, "形成价值", "head", color=COLORS["navy"])
    rows = [
        (("未知协议被强制归类", "新型号/新版本高置信误判"), ("COPD开放集识别", "校准拒识·聚类·漂移归因"), ("持续适配", "发现新协议与版本候选")),
        (("结构与语义断裂", "类别标签无法解释字段含义"), ("EHM-G + MS²R", "四层模型·多证据语义恢复"), ("降低人工成本", "字段与消息候选可追溯")),
        (("单包无法理解行为", "握手/控制/重连缺少状态"), ("连续状态感知", "FSM/EFSM·守卫·在线跟踪"), ("行为可解释", "当前状态与允许下一步")),
        (("识别与安全测试割裂", "异常分数不能直接复核"), ("PCEF一致性闭环", "四类检查·证据·回归"), ("测试可复用", "风险路径转回归用例")),
    ]
    for i,(a,b,c) in enumerate(rows):
        y=170+i*145
        s += box(55,y,400,112,a[0],a[1:],COLORS["green"],COLORS["green_stroke"],COLORS["green_stroke"])
        s += box(600,y,400,112,b[0],b[1:],COLORS["orange"],COLORS["orange_stroke"],COLORS["orange_stroke"])
        s += box(1145,y,400,112,c[0],c[1:],COLORS["blue"],COLORS["navy"],COLORS["navy"])
        s += arrow(455,y+56,592,y+56)
        s += arrow(1000,y+56,1137,y+56)
    save("图2-1_项目痛点研究内容与价值映射",w,h,"项目痛点—研究内容—预期价值映射","问题驱动技术选择，四项研究内容逐一回应真实需求",s)


def fig_3_1():
    w,h=1600,820
    s=group(55,130,690,265,"技术岛A：RF/IQ识别",COLORS["green_stroke"])
    s+=box(90,185,185,130,"信号输入",("IQ/频谱","时频图"),COLORS["green"],COLORS["green_stroke"])
    s+=box(310,185,185,130,"学习方法",("CNN/Transformer","自监督/对比"),COLORS["green"],COLORS["green_stroke"])
    s+=box(530,185,175,130,"典型输出",("制式/设备","飞行模式"),COLORS["green"],COLORS["green_stroke"])
    s+=arrow(275,250,302,250)+arrow(495,250,522,250)
    s+=group(855,130,690,265,"技术岛B：packet/program协议逆向",COLORS["purple_stroke"])
    s+=box(890,185,185,130,"协议输入",("bit/packet","程序/规范"),COLORS["purple"],COLORS["purple_stroke"])
    s+=box(1110,185,185,130,"逆向方法",("对齐/污点","迁移/LLM"),COLORS["purple"],COLORS["purple_stroke"])
    s+=box(1330,185,175,130,"典型输出",("字段/语义","状态机"),COLORS["purple"],COLORS["purple_stroke"])
    s+=arrow(1075,250,1102,250)+arrow(1295,250,1322,250)
    s+=box(565,450,470,105,"尚未打通的研究空白",("未知类、版本演化、连续状态与安全验证缺少统一模型",),COLORS["rose"],COLORS["red"],COLORS["red"])
    s+=path_arrow([(400,395),(400,430),(565,430),(565,480)],"输入层级不可混用")
    s+=path_arrow([(1200,395),(1200,430),(1035,430),(1035,480)],"输出模型难复用")
    s+=group(160,610,1280,145,"本项目的桥接层：统一协议中间表示 + 证据与约束",COLORS["navy"])
    labels=[("开放集与漂移",COLORS["blue"]),("字段语义",COLORS["orange"]),("连续状态",COLORS["purple"]),("约束生成",COLORS["green"]),("一致性与回归",COLORS["yellow"])]
    for i,(lab,fill) in enumerate(labels):
        x=215+i*245
        s+=box(x,650,200,65,lab,(),fill,COLORS["navy"])
        if i: s+=arrow(x-45,682,x-8,682)
    s+=arrow(800,555,800,602,red=True,label="项目突破")
    save("图3-1_研究现状技术岛与项目突破",w,h,"国内外技术路线与项目突破位置","RF前端与协议逆向两座技术岛，通过统一模型连接识别、理解、生成和安全",s)


def fig_4_1():
    w,h=1600,900
    s=group(60,125,1480,130,"合法输入与真值",COLORS["navy"])
    inputs=["公开规范","bit/packet","会话序列","事件/动作日志","可选程序证据"]
    for i,lab in enumerate(inputs):
        x=110+i*290
        s+=box(x,165,230,55,lab,(),COLORS["blue2"],COLORS["navy"])
    s+=arrow(800,255,800,305)
    cards=[
        (100,"① EHM-G",("层次化建模","状态约束生成"),COLORS["orange"],COLORS["orange_stroke"]),
        (470,"② COPD",("开放集拒识","版本漂移发现"),COLORS["blue"],COLORS["navy"]),
        (840,"③ MS²R",("字段语义恢复","连续状态感知"),COLORS["purple"],COLORS["purple_stroke"]),
        (1210,"④ PCEF",("一致性证据","风险与回归"),COLORS["green"],COLORS["green_stroke"]),
    ]
    for i,(x,head,body,fill,stroke) in enumerate(cards):
        s+=box(x,330,290,180,head,body,fill,stroke,stroke)
        if i: s+=arrow(x-70,420,x-8,420)
    s+=group(130,590,1340,190,"共享底座与闭环输出",COLORS["navy"])
    outs=[("四层协议模型",("帧·字段·消息·状态",)),("测试用例库",("合法·边界·异常",)),("风险证据链",("规则·样本·状态",)),("回归与模型修正",("修复前后差异",))]
    for i,(head,body) in enumerate(outs):
        x=185+i*320
        s+=box(x,640,265,95,head,body,COLORS["gray"],COLORS["navy"])
    s+=arrow(800,510,800,582)
    s+=path_arrow([(1360,780),(1360,845),(245,845),(245,518)],"证据与执行结果反馈",red=True,dashed=True)
    save("图4-1_项目总体研究框架",w,h,"项目总体研究框架","四项方法共用统一模型，并通过证据、执行与回归形成可校正闭环",s)


def fig_4_2():
    w,h=1600,850
    s=group(70,125,1040,650,"四层协议中间表示  M = <F, Φ, Σ, Q, Δ, C, E>",COLORS["navy"])
    layers=[
        (180,"会话状态/行为层",("状态Q · 转移Δ · 守卫 · 超时 · 安全约束C",),COLORS["purple"],COLORS["purple_stroke"]),
        (320,"消息层",("类型Σ · 方向 · 请求—响应 · 序列关系",),COLORS["blue"],COLORS["navy"]),
        (460,"字段层",("边界Φ · 类型 · 取值域 · 长度/校验/依赖",),COLORS["orange"],COLORS["orange_stroke"]),
        (600,"帧层",("同步F · 帧长 · 头部 · 载荷 · 完整性",),COLORS["green"],COLORS["green_stroke"]),
    ]
    for i,(y,head,body,fill,stroke) in enumerate(layers):
        s+=box(135,y,900,105,head,body,fill,stroke,stroke)
        if i: s+=arrow(585,y-35,585,y-8)
    s+=group(1170,125,360,650,"证据与验证状态",COLORS["red"])
    ev=[("统计证据","对齐·熵·分布"),("关系证据","长度·序号·校验"),("程序证据","污点·变量传播"),("实验真值","动作·遥测·响应"),("人工确认","候选/验证/冲突")]
    for i,(head,body) in enumerate(ev):
        y=180+i*112
        fill=[COLORS["blue2"],COLORS["yellow"],COLORS["purple"],COLORS["green"],COLORS["rose"]][i]
        s+=box(1215,y,270,78,head,(body,),fill,COLORS["navy"])
        s+=arrow(1162,y+39,1112,y+39,red=(i==4),dashed=True)
    s+=t(800,820,"同一对象标识贯通识别、生成、状态跟踪、一致性分析与回归", "head")
    save("图4-2_四层协议中间表示与证据链",w,h,"四层协议中间表示与证据链","模型不是一张字段表，而是带证据、冲突与版本的可执行知识底座",s)


def pipeline(name,title,subtitle,steps,groups=None,decision_at=None,feedback=None):
    w,h=1600,760
    s=""
    y1,y2=210,470
    bw,bh=250,110
    xs=[70,380,690,1000,1310]
    positions=[]
    for i,st in enumerate(steps):
        if i<5: x,y=xs[i],y1
        else: x,y=xs[9-i],y2
        positions.append((x,y))
        fill=[COLORS["blue"],COLORS["orange"],COLORS["purple"],COLORS["green"],COLORS["yellow"]][i%5]
        stroke=[COLORS["navy"],COLORS["orange_stroke"],COLORS["purple_stroke"],COLORS["green_stroke"],COLORS["orange_stroke"]][i%5]
        s+=box(x,y,bw,bh,st[0],st[1:],fill,stroke,stroke)
    for i in range(1,min(5,len(positions))): s+=arrow(positions[i-1][0]+bw,positions[i-1][1]+55,positions[i][0]-8,positions[i][1]+55)
    if len(positions)>5:
        s+=path_arrow([(positions[4][0]+bw,positions[4][1]+55),(1580,positions[4][1]+55),(1580,positions[5][1]+55),(positions[5][0]+bw+8,positions[5][1]+55)])
        for i in range(6,len(positions)): s+=arrow(positions[i-1][0]-8,positions[i-1][1]+55,positions[i][0]+bw+8,positions[i][1]+55)
    if groups:
        for x,y,gx,gy,label,color in groups: s+=group(x,y,gx,gy,label,color)
    if feedback:
        s+=path_arrow(feedback,"反馈修正",red=True,dashed=True)
    save(name,w,h,title,subtitle,s)


def fig_6_1():
    steps=[
        ("数据登记","来源·版本·授权"),("会话切分","方向·时间窗"),("已知/未知","校准与拒识"),("结构语义","字段·消息关系"),("连续状态","FSM/EFSM"),
        ("统一模型","证据·冲突·版本"),("约束生成","合法·边界·异常"),("一致性检查","语法·字段·时序·状态"),("风险证据","规则·样本·解释"),("回归修正","修复前后比较")]
    pipeline("图6-1_项目总体技术路线","项目总体技术路线","从合法数据到风险证据与模型修正的十步主路径",steps,feedback=[(70,580),(40,580),(40,120),(225,120),(225,202)])


def fig_6_2():
    steps=[
        ("输入与真值","规范·报文·会话"),("四层建模","F·Φ·Σ·Q/Δ"),("证据管理","候选·验证·冲突"),("约束编译","语法·字段·状态"),("合法基线","通过全部约束"),
        ("边界/异常","单变量受控违反"),("隔离执行","速率限制·急停"),("响应判定","接受·拒绝·超时"),("差异分析","期望与实际"),("模型修正","版本与回退")]
    pipeline("图6-2_层次化建模与状态约束生成","路线一：层次化建模与状态约束生成","EHM-G把协议知识编译为可执行测试，并用响应反向修正模型",steps,feedback=[(70,580),(40,580),(40,120),(505,120),(505,202)])


def fig_6_3():
    w,h=1600,820
    s=box(70,330,230,100,"会话样本",("协议·版本·设备",),COLORS["blue2"],COLORS["navy"])
    s+=arrow(300,380,390,380)
    s+=box(400,330,240,100,"可解释特征",("长度·方向·周期·序列",),COLORS["blue"],COLORS["navy"])
    s+=arrow(640,380,720,380)
    s+=box(730,330,240,100,"已知类模型",("独立校准集",),COLORS["orange"],COLORS["orange_stroke"])
    s+=arrow(970,380,1050,380)
    s+=decision(1160,380,190,130,"可信域内？")
    s+=arrow(1255,380,1390,380,"是")
    s+=box(1400,325,150,110,"已知类别",("概率+证据",),COLORS["green"],COLORS["green_stroke"])
    s+=arrow(1160,445,1160,540,"否",red=True)
    s+=box(990,550,340,95,"未知样本聚类",("簇稳定性·代表样本",),COLORS["purple"],COLORS["purple_stroke"])
    s+=arrow(990,597,850,597)
    s+=box(590,550,250,95,"漂移归因",("协议/版本/环境",),COLORS["yellow"],COLORS["orange_stroke"])
    s+=arrow(590,597,450,597)
    s+=box(180,550,260,95,"人工确认与更新",("证据·版本·可回退",),COLORS["green"],COLORS["green_stroke"])
    s+=path_arrow([(310,550),(310,490),(850,490),(850,438)],"协议库增量",dashed=True)
    s+=group(55,145,1500,565,"会话级划分 · 跨版本/设备/采集条件验证 · 同一会话不得跨集合",COLORS["navy"])
    save("图6-3_开放集识别与版本漂移发现",w,h,"路线二：开放集识别与版本漂移发现","先校准、再拒识；先排除采集漂移、再确认协议或版本演化",s)


def fig_6_4():
    w,h=1600,820
    s=group(50,130,400,600,"多源证据输入",COLORS["navy"])
    ev=[("流量统计","对齐·熵·分布"),("关系验证","长度·序号·CRC"),("程序证据","污点·变量传播"),("受控动作","遥测·响应·日志")]
    for i,(a,b) in enumerate(ev): s+=box(95,190+i*125,310,80,a,(b,),[COLORS["blue"],COLORS["yellow"],COLORS["purple"],COLORS["green"]][i],COLORS["navy"])
    stages=[("字段边界候选",("边界分数Sb(i)",)),("语义与关系",("类型·依赖·证据",)),("消息关联",("方向·邻近·响应",)),("状态机推断",("状态·转移·守卫",)),("在线跟踪",("当前状态·下一步",))]
    for i,(a,b) in enumerate(stages):
        x=520+i*205
        y=320 if i%2==0 else 470
        s+=box(x,y,170,105,a,b,[COLORS["orange"],COLORS["blue"],COLORS["green"],COLORS["purple"],COLORS["yellow"]][i],COLORS["navy"])
        if i: s+=arrow(520+(i-1)*205+170,(320 if (i-1)%2==0 else 470)+52,x-8,y+52)
    for i in range(4): s+=arrow(450,230+i*125,510,372 if i<2 else 522,dashed=True)
    s+=box(1050,650,470,75,"输出",("字段/消息/状态候选 · 置信度 · 证据索引 · 歧义路径",),COLORS["blue2"],COLORS["navy"],COLORS["navy"])
    s+=arrow(1510,522,1510,642)
    save("图6-4_字段语义恢复与连续状态感知",w,h,"路线三：字段语义恢复与连续状态感知","证据可降级：没有程序仍可运行统计/校验基线，有程序再增强语义",s)


def fig_6_5():
    w,h=1600,850
    s=box(60,330,240,110,"实时/离线会话",("已确认模型+当前状态",),COLORS["blue2"],COLORS["navy"])
    checks=[("语法一致性","帧·长度·校验",COLORS["blue"]),("字段一致性","范围·依赖",COLORS["orange"]),("时序一致性","频率·超时·重放",COLORS["yellow"]),("状态一致性","守卫·非法转移",COLORS["purple"])]
    for i,(a,b,fill) in enumerate(checks):
        y=145+i*150
        s+=box(430,y,270,95,a,(b,),fill,COLORS["navy"])
        s+=arrow(300,385,420,y+47,dashed=True)
        s+=arrow(700,y+47,830,385)
    s+=box(840,315,290,140,"证据融合",("违规向量 vₜ","异常分数 aₜ","证据可靠度 rₜ"),COLORS["green"],COLORS["green_stroke"],COLORS["green_stroke"])
    s+=arrow(1130,385,1215,385)
    s+=decision(1320,385,190,135,"达到门槛？")
    s+=arrow(1415,385,1535,385,"是",red=True)
    s+=box(1395,540,155,95,"风险证据链",("规则·样本·状态",),COLORS["rose"],COLORS["red"])
    s+=path_arrow([(1535,385),(1570,385),(1570,587),(1558,587)],red=True)
    s+=box(1110,650,250,90,"人工复核",("确认/降级/驳回",),COLORS["orange"],COLORS["orange_stroke"])
    s+=arrow(1395,587,1235,642)
    s+=box(700,650,300,90,"回归测试",("前置状态·输入·期望",),COLORS["blue"],COLORS["navy"])
    s+=arrow(1102,695,1008,695)
    s+=path_arrow([(700,695),(340,695),(340,445),(300,445)],"规则与模型更新",red=True,dashed=True)
    save("图6-5_协议一致性证据融合与回归验证",w,h,"路线四：协议一致性证据融合与回归验证","异常分数不能单独升级为攻击；高风险必须具备可定位协议证据",s)


def fig_8_1():
    w,h=1600,760
    s=t(800,140,"12个月：先底座、后算法；先单机闭环、后可选扩展", "head")
    y=360
    s+=f'<line x1="100" y1="{y}" x2="1510" y2="{y}" stroke="{COLORS["navy"]}" stroke-width="4" marker-end="url(#arrow)"/>'
    phases=[
        (1,2,"需求与模型",("文献复核","数据/IR规范"),COLORS["blue"]),
        (3,4,"数据与识别",("数据集V1","闭集/开放集"),COLORS["green"]),
        (5,6,"结构与语义",("字段/消息","评测报告"),COLORS["orange"]),
        (7,8,"状态感知",("FSM/EFSM","在线跟踪"),COLORS["purple"]),
        (9,10,"生成与安全",("测试用例","风险证据"),COLORS["yellow"]),
        (11,11,"系统集成",("跨版本/消融","用户试用"),COLORS["blue2"]),
        (12,12,"成果固化",("软著/专利/论文","PPT与答辩"),COLORS["rose"]),
    ]
    scale=115
    for i,(m1,m2,head,body,fill) in enumerate(phases):
        cx=100+((m1+m2)/2-0.5)*scale
        width=max(150,(m2-m1+1)*scale-18)
        x=cx-width/2
        above=i%2==0
        by=190 if above else 435
        s+=box(x,by,width,115,head,body,fill,COLORS["navy"])
        s+=f'<circle cx="{cx}" cy="{y}" r="10" fill="#FFFFFF" stroke="{COLORS["navy"]}" stroke-width="4"/>'
        s+=f'<line x1="{cx}" y1="{y + (-10 if above else 10)}" x2="{cx}" y2="{by+115 if above else by}" stroke="{COLORS["navy"]}" stroke-width="2"/>'
        s+=t(cx,y+45 if above else y-28,f"M{m1}"+(f"–M{m2}" if m2!=m1 else ""),"label")
    s+=group(95,610,1410,95,"贯穿全周期：数据合规 · 版本管理 · 周迭代 · 失败记录 · 人工复核 · 可重复实验",COLORS["red"])
    save("图8-1_十二个月实施路线图",w,h,"十二个月实施路线图","每两个月形成可验收中间成果，第11个月打通系统，第12个月固化成果",s)


def main():
    fig_2_1(); fig_3_1(); fig_4_1(); fig_4_2(); fig_6_1(); fig_6_2(); fig_6_3(); fig_6_4(); fig_6_5(); fig_8_1()
    readme = """# 绘图代码说明\n\n本文件夹内的10个SVG均为可编辑图片代码，`generate_diagrams.py`可重新生成全部SVG。\n\n- 风格：参照天津大学创新训练申报书，采用白底、浅色分区、虚线分组、蓝色箭头和红色关键问题强调。\n- 编辑：可用浏览器、Inkscape、Adobe Illustrator、Figma或PowerPoint打开SVG继续调整。\n- 插入：PNG预览存放在相邻的“图片素材”文件夹；DOCX按用户要求只保留插图标记。\n- 提醒：老师要求最终提交版实际插入图片，定稿时必须用这些图替换占位段落。\n"""
    (ROOT / "绘图代码说明.md").write_text(readme, encoding="utf-8")
    print("generated", len(list(ROOT.glob("*.svg"))), "svg files")


if __name__ == "__main__":
    main()
