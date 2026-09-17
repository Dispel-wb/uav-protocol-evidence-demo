from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'final_svg'
OUT.mkdir(exist_ok=True)
INK='#29353B'; MUTED='#566169'; RULE='#A7AFB1'; TEAL='#496B77'; RUST='#956B50';
LIGHT='#F5F7F7'; WARM='#FCF8F3'; PAPER='#FFFFFF'; GREY='#F4F5F4'

def E(v): return escape(str(v))
def txt(x,y,s,size=27,weight=400,color=INK,anchor='start'):
 return f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" font-size="{size}" font-weight="{weight}">{E(s)}</text>'
def rect(x,y,w,h,fill=PAPER,stroke=RULE,sw=2,rx=0):
 return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
def path(d,color=INK,sw=2.5,dash=None,fill='none'):
 return f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>'
def arr(x,y,direction='r',color=INK):
 if direction=='r': d=f'M{x-11} {y-7} L{x} {y} L{x-11} {y+7}'
 elif direction=='l': d=f'M{x+11} {y-7} L{x} {y} L{x+11} {y+7}'
 elif direction=='d': d=f'M{x-7} {y-11} L{x} {y} L{x+7} {y-11}'
 else: d=f'M{x-7} {y+11} L{x} {y} L{x+7} {y+11}'
 return path(d,color)
def io(x,y,w,h,fill=PAPER,stroke=TEAL):
 return path(f'M{x+22} {y} H{x+w} L{x+w-22} {y+h} H{x} Z',stroke,2,fill=fill)
def diamond(cx,cy,w,h,fill=WARM,stroke=RUST):
 return path(f'M{cx} {cy-h/2} L{cx+w/2} {cy} L{cx} {cy+h/2} L{cx-w/2} {cy} Z',stroke,2.5,fill=fill)
def base():
 return ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 760">',
 '<style>text{font-family:"Microsoft YaHei","Noto Sans SC",sans-serif}</style>',
 f'<rect width="1600" height="760" fill="{PAPER}"/>']
def save(prefix,s):
 names={
  '图2-1':'图2-1_项目痛点研究内容与价值映射.svg',
  '图3-1':'图3-1_研究现状技术岛与项目突破.svg',
  '图4-1':'图4-1_项目总体研究框架.svg',
  '图4-2':'图4-2_四层协议中间表示与证据链.svg',
  '图6-5':'图6-5_协议一致性证据融合与回归验证.svg',
 }
 (OUT/names[prefix]).write_text(''.join(s)+'</svg>',encoding='utf-8')


INK='#23292F'; MUTED='#5B6268'; RULE='#AAB1B5'; BLUE='#004488'; WINE='#994455';
PALE_BLUE='#EAF0F6'; PALE_WINE='#F6EDF0'; PAPER='#FFFFFF'

def mono(x,y,s,size=25,color=INK,anchor='start'):
 from html import escape
 return f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" font-family="Consolas,monospace" font-size="{size}">{escape(s)}</text>'

def label(x,y,n,title):
 return [txt(x,y,n,27,700,BLUE),txt(x+48,y,title,29,700,INK)]

# 2-1. Explicit gap / experimental intervention / acceptance evidence.
s=base()
s += [txt(72,65,'观察到的断点',29,700),txt(540,65,'研究动作',29,700),txt(1104,65,'验收证据',29,700),path('M72 91 H1530',INK,2)]
rows=[
 ('01','版本漂移','同一消息在不同版本中变长','开放集拒识 → 人工核验版本','跨版本留出集；未知版本拒识率'),
 ('02','字段语义','字节边界已知，含义仍不确定','动作日志与报文联动推断','字段来源、置信度、冲突记录'),
 ('03','交互状态','单帧合法，顺序仍可能违规','守卫条件与在线状态跟踪','ARM→TAKEOFF 序列回放结果'),
 ('04','结论复核','异常报告难定位到原始样本','证据索引 + 失败样本回归','消息号、前后状态、版本、用例')]
for i,(n,h,example,action,evidence) in enumerate(rows):
 y=119+i*139
 s += [txt(72,y+35,n,26,700,BLUE),txt(125,y+35,h,29,700),txt(125,y+78,example,24,color=MUTED),
       txt(540,y+51,action,27),txt(1104,y+51,evidence,26),
       path(f'M485 {y+46} H521',RULE,2),arr(521,y+46,color=RULE),path(f'M1032 {y+46} H1080',RULE,2),arr(1080,y+46,color=RULE),
       path(f'M72 {y+111} H1530',RULE,1)]
s += [txt(72,723,'每个输出都能回溯到样本、版本和实验动作；不能确认的字段保留候选状态。',25,color=MUTED)]
save('图2-1',s)

# 3-1. Research coverage as a genuine matrix, with endpoint descriptions.
s=base()
xs=[692,858,1024,1190,1356]
s += [txt(73,60,'研究路线',29,700),txt(73,103,'典型产物',24,color=MUTED)]
for x,h in zip(xs,['信号发现','帧结构','字段语义','交互状态','测试回归']):s += [txt(x,69,h,25,700,anchor='middle')]
s += [path('M73 121 H1523',INK,2)]
rows=[('射频 / 设备识别','设备或信号类型',[1,0,0,0,0]),('流量逆向','帧格式与候选字段',[0,1,1,0,0]),('程序执行分析','处理路径与语义线索',[0,1,1,1,0]),('状态学习','交互模型与测试序列',[0,0,0,1,1]),('本项目：统一证据模型','跨层、跨版本的可回归结论',[1,1,1,1,1])]
for i,(h,sub,vals) in enumerate(rows):
 y=145+i*105
 if i==4:s += [path(f'M73 {y-7} H1523 V{y+87} H73 Z',BLUE,1.4,fill=PALE_BLUE)]
 s += [txt(73,y+34,h,27,700 if i==4 else 400,BLUE if i==4 else INK),txt(73,y+70,sub,22,color=MUTED)]
 for x,v in zip(xs,vals):
  if v:s += [f'<circle cx="{x}" cy="{y+43}" r="10" fill="{BLUE if i==4 else INK}"/>']
  else:s += [f'<circle cx="{x}" cy="{y+43}" r="10" fill="white" stroke="{RULE}" stroke-width="2"/>']
 s += [path(f'M73 {y+88} H1523',RULE,1)]
s += [txt(73,726,'实心：该路线的主要产物；空心：不能据此独立支持的能力。',24,color=MUTED)]
save('图3-1',s)

# 4-1. Architecture with trace/field/state artifacts, instead of generic cards.
s=base()
s += [txt(70,65,'A  输入与标注',29,700),txt(505,65,'B  层次建模',29,700),txt(1070,65,'C  验证与回写',29,700),path('M70 90 H1530',INK,2)]
# Input trace ledger
s += [txt(70,136,'会话 07 / 仿真版本 1.0',25,700),path('M70 151 H420',RULE,1),
      mono(70,200,'00:01.000  ARM      #02',24),mono(70,245,'00:01.120  ACK      #03',24),mono(70,290,'00:02.000  TAKEOFF  #04',24),
      txt(70,352,'附：动作日志、公开规范、程序证据',23,color=MUTED),path('M430 235 H480',BLUE,2.5),arr(480,235,color=BLUE)]
# Data model not boxes: field ruler and state diagram
s += [txt(505,136,'帧字段对齐',26,700),path('M505 151 H1000',RULE,1)]
parts=[('同步',505,73),('长度',578,80),('类型',658,90),('载荷',748,166),('校验',914,86)]
for j,(h,x,w) in enumerate(parts):
 s += [rect(x,181,w,72,PALE_BLUE if j in (2,3) else PAPER,BLUE if j in (2,3) else RULE,1.5),txt(x+w/2,226,h,23,anchor='middle')]
s += [mono(505,291,'7E   05   02   0C 00   A1',24,color=BLUE),txt(505,351,'字段语义附来源与置信度',23,color=MUTED)]
s += [txt(505,427,'消息与状态约束',26,700),path('M505 442 H1000',RULE,1)]
states=[('待机',565),('已解锁',710),('飞行中',880)]
for h,x in states:s += [f'<circle cx="{x}" cy="{x*0+540}" r="48" fill="white" stroke="{BLUE}" stroke-width="2"/>',txt(x,548,h,23,anchor='middle')]
s += [path('M613 540 H662',BLUE,2.2),arr(662,540,color=BLUE),txt(637,512,'ARM',20,color=MUTED,anchor='middle'),
      path('M758 540 H832',BLUE,2.2),arr(832,540,color=BLUE),txt(795,512,'TAKEOFF',20,color=MUTED,anchor='middle')]
# Check ledger + explicit feedback
s += [path('M1014 232 H1050',BLUE,2.5),arr(1050,232,color=BLUE),txt(1070,136,'一致性检查',26,700),path('M1070 151 H1530',RULE,1),
      txt(1070,202,'语法  /  字段  /  时序  /  状态',25),path('M1070 223 H1530',RULE,1),
      txt(1070,286,'通过：证据充分并可重放',25,color=BLUE),txt(1070,338,'待确认：保留候选与冲突',25,color=WINE),
      path('M1070 373 H1530',RULE,1),txt(1070,427,'输出记录',26,700),
      mono(1070,478,'case: 07-ARM-TAKEOFF',23),mono(1070,520,'source: frame #02-#04',23),mono(1070,562,'version: AeroLab 1.0',23)]
s += [path('M1305 608 V662 H360 V377',WINE,2,'8 7'),arr(360,377,'u',WINE),
      txt(780,699,'验证失败 → 补充样本与实验 → 模型修订',25,color=WINE,anchor='middle')]
save('图4-1',s)

# 4-2. Four-layer representation shown with a single aligned example and evidence provenance.
s=base()
s += [txt(72,63,'同一条仿真会话证据在四层模型中的投影',29,700),path('M72 87 H1530',INK,2)]
rows=[
 ('01','帧','7E | 05 | 02 | 0C 00 | A1','同步、长度、类型、载荷、校验'),
 ('02','字段','type=02; altitude=12 m','边界、编码、单位、取值范围'),
 ('03','消息','TAKEOFF; GCS → UAV','方向、请求响应、消息序号'),
 ('04','状态','ARMED → FLYING','守卫、超时、允许的下一步')]
for i,(n,h,example,desc) in enumerate(rows):
 y=126+i*132
 s += [txt(72,y+31,n,25,700,BLUE),txt(139,y+31,h,30,700),path(f'M206 {y-3} V{y+84}',RULE,1),
       mono(240,y+31,example,26,BLUE if i<2 else INK),txt(240,y+72,desc,24,color=MUTED),
       path(f'M72 {y+104} H1025',RULE,1)]
 if i<3:s += [path(f'M176 {y+104} V{y+130}',BLUE,1.5),arr(176,y+130,'d',BLUE)]
s += [path('M1090 123 V633',BLUE,2.2),txt(1130,143,'证据来源',29,700)]
ev=[('E1','报文字节与时间戳',207),('E2','实验动作及设备响应',322),('E3','公开规范 / 程序路径',437),('E4','版本、冲突与人工确认',552)]
for n,t,y in ev:
 s += [f'<circle cx="1090" cy="{y}" r="6" fill="{BLUE}"/>',path(f'M1090 {y} H1120',BLUE,1.5),txt(1130,y+9,n,23,700,BLUE),txt(1181,y+9,t,23)]
s += [path('M72 703 H1530',RULE,1),txt(72,740,'候选值与已验证值分开保存；只有来源、实验和版本均可追溯时才升级结论。',24,color=MUTED)]
save('图4-2',s)

# 6-5. Checks and audit record with one concrete failure, not a generic four-box pipeline.
s=base()
s += [txt(72,65,'并行约束',29,700),txt(655,65,'定位与交叉核验',29,700),txt(1210,65,'输出记录',29,700),path('M72 90 H1530',INK,2)]
checks=[('语法','帧长 / 校验 / 编码','通过'),('字段','高度 0–120 m','通过'),('时序','序号严格递增','冲突'),('状态','起飞前必须解锁','冲突')]
for i,(h,d,v) in enumerate(checks):
 y=135+i*113
 s += [txt(72,y+27,h,27,700),txt(175,y+27,d,25),
       txt(520,y+27,v,24,700,BLUE if v=='通过' else WINE),path(f'M72 {y+72} H622',RULE,1)]
s += [path('M625 190 H655',RULE,2),arr(655,190,color=RULE),
      txt(655,150,'案例：第 02 条 TAKEOFF',26,700),path('M655 174 H1138',RULE,1),
      mono(655,232,'seq=2; state=待机',24),txt(655,286,'序号前值：2  →  本条：2',24),
      txt(655,331,'状态守卫：需先接收 ARM',24,color=WINE),
      txt(655,405,'证据交叉',26,700),path('M655 427 H1138',RULE,1),
      txt(655,470,'原始消息 #02 + 会话前态 + 规则版本',24),
      txt(655,513,'冲突定位到消息与状态，不推断设备故障',23,color=MUTED)]
s += [path('M1155 300 H1190',BLUE,2),arr(1190,300,color=BLUE),
      txt(1210,150,'finding 02',26,700,BLUE),path('M1210 174 H1530',RULE,1),
      txt(1210,232,'类别：状态约束',24),txt(1210,278,'消息：TAKEOFF',24),
      txt(1210,324,'前态：待机',24),txt(1210,370,'结论：待复核',24,color=WINE),
      txt(1210,416,'索引：session07/#02',23),path('M1210 449 H1530',RULE,1),
      txt(1210,493,'修复后回归',26,700),txt(1210,540,'更新用例与模型版本',23)]
s += [path('M1370 585 V662 H376 V603',WINE,2,'8 7'),arr(376,603,'u',WINE),
      txt(785,709,'异常报告保留原始输入与规则版本；人工复核后进入回归测试库。',24,color=MUTED,anchor='middle')]
save('图6-5',s)
print('rewritten five evidence-led figures')
