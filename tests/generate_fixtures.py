"""Regenerate sample captures with the official pymavlink encoder.

Development-only: PYTHONPATH must include pymavlink. The browser demo has no dependency.
"""
from pathlib import Path
import json
from pymavlink.dialects.v20 import common as v2
from pymavlink.dialects.v10 import common as v1

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'samples';OUT.mkdir(exist_ok=True)

def packet(dialect, message, system, component, seq):
    mav=dialect.MAVLink(None)
    mav.srcSystem=system;mav.srcComponent=component;mav.seq=seq
    return message.pack(mav)

def hb(armed=False):return v2.MAVLink_heartbeat_message(2,3,128 if armed else 0,0,4,3)
def cmd(command,param1=0,param7=0):return v2.MAVLink_command_long_message(1,1,command,0,param1,0,0,0,0,0,param7)
def ack(command,result=0):return v2.MAVLink_command_ack_message(command,result,0,0,255,190)
def gps(fix=3):return v2.MAVLink_gps_raw_int_message(12345678,fix,399876543,1161234567,50000,120,130,500,0,12,0,0,0,0,0,0)

def sbus(channels,flags=0):
    assert len(channels)==16
    out=bytearray(25);out[0]=0x0f
    for i,v in enumerate(channels):
        assert 0<=v<=2047
        bit=i*11
        for k in range(11):
            if v & (1<<k):out[1+(bit+k)//8] |= 1<<((bit+k)%8)
    out[23]=flags;out[24]=0
    return bytes(out)

normal=b''.join([
 packet(v2,hb(False),1,1,0), packet(v2,gps(3),1,1,1),
 packet(v2,cmd(400,1),255,190,0), packet(v2,ack(400),1,1,2),
 packet(v2,hb(True),1,1,3), packet(v2,cmd(22,0,50),255,190,1),
 packet(v2,ack(22),1,1,4),
])
anomaly=b''.join([packet(v2,hb(False),1,1,0),packet(v2,gps(2),1,1,1),packet(v2,cmd(22,0,180),255,190,0)])
mav1=b''.join([
 packet(v1,v1.MAVLink_heartbeat_message(2,3,0,0,4,3),1,1,0),
 packet(v1,v1.MAVLink_attitude_message(1000,0.1,-0.2,1.2,0,0,0),1,1,1),
])
healthy=sbus([1024]*16)+sbus([1100,900,1000,1200]+[1024]*12)
failsafe=sbus([1024]*16,8)
lost=sbus([1024]*16,4)+sbus([1024]*16,4)+sbus([1024]*16,0)
corrupt=bytearray(packet(v2,hb(False),1,1,0));corrupt[-1]^=0x80
mixed=packet(v2,hb(False),1,1,0)+sbus([1024]*16)+packet(v2,gps(3),1,1,1)

fixtures={
 'mavlink2-normal':('MAVLink 2 · 正常解锁与起飞',normal),
 'mavlink2-anomaly':('MAVLink 2 · 未解锁/低定位/超高起飞',anomaly),
 'mavlink1-telemetry':('MAVLink 1 · 心跳与姿态',mav1),
 'sbus-healthy':('SBUS · 正常通道',healthy),
 'sbus-failsafe':('SBUS · 失控保护标志',failsafe),
 'sbus-lost':('SBUS · 连续丢帧',lost),
 'mavlink-crc-error':('MAVLink 2 · CRC 损坏',bytes(corrupt)),
 'mixed-capture':('混合捕获 · MAVLink 与 SBUS',mixed),
}
catalog=[]
for key,(title,data) in fixtures.items():
    (OUT/f'{key}.hex').write_text(data.hex(' ').upper()+'\n',encoding='utf-8')
    catalog.append({'id':key,'title':title,'hex':data.hex(' ').upper(),'bytes':len(data)})
(OUT/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'src'/'samples.js').write_text('window.ProtocolSamples = '+json.dumps(catalog,ensure_ascii=False,indent=2)+';\n',encoding='utf-8')
print('generated',len(catalog),'captures')
