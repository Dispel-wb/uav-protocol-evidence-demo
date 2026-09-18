"""Reproducible *undocumented* trace fixtures; discovery does not import this layout."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
catalog=root/'samples'/'catalog.json'
items=json.loads(catalog.read_text(encoding='utf-8'))

def packet(magic, payload, kind, seq, length_at, checksum):
    body=list(magic)
    if length_at==2:
        body += [len(payload), kind, seq]
    else:
        body += [kind, len(payload), seq]
    body += payload
    check=(sum(body)&255) if checksum=='sum8' else 0
    if checksum=='xor8':
        for b in body: check^=b
    return body+[check]

a=[packet([0xA6,0x5C],p,0x31+i%2,i,2,'sum8') for i,p in enumerate([[0x13,0x52,0x27],[0x42,0x17,0x63,0x28],[0x29,0x78,0x44],[0x64,0x35,0x11,0x48,0x22]])]
b=[packet([0x7B,0xD2],p,0x41+i%2,i,3,'xor8') for i,p in enumerate([[0x55,0x38,0x71,0x26],[0x33,0x66,0x19],[0x49,0x24,0x75,0x12,0x53],[0x68,0x31,0x46,0x22]])]
mixed=[]
for x,y in zip(a,b): mixed+=x+y
normal=next(x for x in items if x['id']=='mavlink2-normal')
known=[int(x,16) for x in normal['hex'].split()][:21]
mixed_known=a[0]+b[0]+a[1]+known+b[1]+a[2]+b[2]+a[3]+b[3]
for id,title,data in [
    ('unknown-two-families','未知协议 · 两种交错帧结构',mixed),
    ('known-unknown-mix','已知 + 未知 · 三种协议混合',mixed_known),
]:
    if any(x in (0xFD,0xFE,0x0F) for packet_bytes in a+b for x in packet_bytes):
        raise ValueError('Fixture contains known-protocol sync byte')
    entry={'id':id,'title':title,'hex':' '.join(f'{x:02X}' for x in data),'bytes':len(data)}
    items=[x for x in items if x['id']!=id]+[entry]
    (root/'samples'/f'{id}.hex').write_text(entry['hex']+'\n',encoding='utf-8')
catalog.write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(root/'src'/'samples.js').write_text('window.ProtocolSamples = '+json.dumps(items,ensure_ascii=False,indent=2)+';\n',encoding='utf-8')
print('generated',len(items),'fixtures')
