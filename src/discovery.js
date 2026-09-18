/* Trace-based structure discovery for unknown, unencrypted byte streams.
   Hypotheses are evidence, never a claim of protocol identity or field meaning. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ProtocolDiscovery = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const key = (bytes, at) => `${bytes[at].toString(16).padStart(2,'0')}${bytes[at+1].toString(16).padStart(2,'0')}`.toUpperCase();
  const sum8 = data => data.reduce((a,b) => (a+b)&255, 0);
  const xor8 = data => data.reduce((a,b) => a^b, 0);
  const hex = data => Array.from(data, b => b.toString(16).padStart(2,'0').toUpperCase()).join(' ');

  function infer(input, gaps) {
    const bytes = input instanceof Uint8Array ? input : Uint8Array.from(input);
    const mask = new Uint8Array(bytes.length);
    for (const gap of gaps) mask.fill(1, gap.offset, gap.offset + gap.length);
    const occurrences = new Map();
    for (let at=0; at+1<bytes.length; at++) {
      if (!mask[at] || !mask[at+1]) continue;
      const k=key(bytes,at);
      if (!occurrences.has(k)) occurrences.set(k,[]);
      occurrences.get(k).push(at);
    }
    const candidates=[];
    for (const [magic, positions] of occurrences) {
      if (positions.length<3 || positions.length>48) continue;
      for (let lengthOffset=2; lengthOffset<=5; lengthOffset++) {
        for (let overhead=Math.max(lengthOffset+2,4); overhead<=10; overhead++) {
          const packets=[];
          for (const at of positions) {
            if (at+lengthOffset>=bytes.length || !mask[at+lengthOffset]) continue;
            const size=bytes[at+lengthOffset]+overhead;
            if (size<overhead || size>128 || at+size>bytes.length) continue;
            if (mask.slice(at,at+size).some(v=>!v)) continue;
            packets.push({offset:at,length:size,raw:hex(bytes.slice(at,at+size))});
          }
          if (packets.length<3) continue;
          const checks=['sum8','xor8'].map(kind => ({kind,count:packets.filter(p => {
            const body=bytes.slice(p.offset,p.offset+p.length-1);
            return (kind==='sum8'?sum8(body):xor8(body))===bytes[p.offset+p.length-1];
          }).length})).sort((a,b)=>b.count-a.count);
          const checksum=checks[0].count===packets.length?checks[0].kind:null;
          // Without a verified checksum, contiguous repeated framing is only a weak hypothesis.
          const adjacent=packets.filter(p=>positions.includes(p.offset+p.length)).length;
          if (!checksum && !(packets.length>=4 && adjacent>=2)) continue;
          const uniqueLengths=new Set(packets.map(p=>p.length)).size;
          const score=(checksum?100:0)+packets.length*8+uniqueLengths*2+adjacent;
          candidates.push({magic,lengthOffset,overhead,checksum,packets,score});
        }
      }
    }
    candidates.sort((a,b)=>b.score-a.score || b.packets.length-a.packets.length);
    const used=new Uint8Array(bytes.length), families=[];
    for (const c of candidates) {
      const packets=c.packets.filter(p=>!used.slice(p.offset,p.offset+p.length).some(Boolean));
      if (packets.length<3 || families.length>=5) continue;
      const minLength=Math.min(...packets.map(p=>p.length));
      const columns=[];
      let sequenceIdentified=false;
      for (let at=0;at<Math.min(minLength,12);at++) {
        const values=packets.map(p=>bytes[p.offset+at]);
        const distinct=new Set(values).size;
        if (at===c.lengthOffset) columns.push({offset:at,label:'候选长度',evidence:`帧长 = 此字节 + ${c.overhead}`});
        else if (at<2) columns.push({offset:at,label:'重复同步字节',evidence:hex(bytes.slice(packets[0].offset+at,packets[0].offset+at+1))});
        else if (at===minLength-1 && c.checksum) continue;
        else if (distinct===1) columns.push({offset:at,label:'固定值',evidence:`0x${values[0].toString(16).padStart(2,'0').toUpperCase()}`});
        else if (!sequenceIdentified && at>c.lengthOffset && distinct===packets.length && values.every((v,i)=>i===0 || v===((values[i-1]+1)&255))) {
          columns.push({offset:at,label:'候选序号',evidence:values.join(' → ')}); sequenceIdentified=true;
        }
        else if (distinct>1 && distinct<=Math.max(2,Math.floor(packets.length/2))) columns.push({offset:at,label:'候选类型',evidence:[...new Set(values)].map(v=>`0x${v.toString(16).padStart(2,'0').toUpperCase()}`).join(' / ')});
      }
      const payloadStart=Math.max(c.lengthOffset+1,...columns.filter(x=>['候选类型','候选序号'].includes(x.label)).map(x=>x.offset+1));
      if (payloadStart < minLength-(c.checksum?1:0)) columns.push({offset:`+${payloadStart}…`,label:'候选可变区',evidence:c.checksum?'至末字节校验前':'至帧末'});
      if (c.checksum) columns.push({offset:'末尾',label:'候选校验',evidence:c.checksum});
      packets.forEach(p=>used.fill(1,p.offset,p.offset+p.length));
      families.push({id:`未知族 ${families.length+1}`,magic:c.magic,packetCount:packets.length,lengthOffset:c.lengthOffset,overhead:c.overhead,checksum:c.checksum,confidence:c.checksum?'较高：重复结构且校验一致':'较低：仅重复结构',columns,packets,observations:[`双字节前缀 ${c.magic.match(/../g).join(' ')}`,`长度候选位于 +${c.lengthOffset}，总长 = 值 + ${c.overhead}`,c.checksum?`末字节与 ${c.checksum} 校验在 ${packets.length} 帧均一致`:'未发现可验证的校验规则']});
    }
    const unexplained=[];
    let start=-1;
    for (let at=0;at<=bytes.length;at++) {
      if (at<bytes.length && mask[at] && !used[at]) { if (start<0) start=at; }
      else if (start>=0) { unexplained.push({offset:start,length:at-start,raw:hex(bytes.slice(start,at))}); start=-1; }
    }
    return {families,unexplained,unexplainedBytes:unexplained.reduce((n,g)=>n+g.length,0),minimumEvidence:'至少 3 帧同族数据；缺少重复样本时无法推断字段。',limits:'仅从字节统计与候选校验推断结构；不能从孤立字节证明字段业务含义、协议名称、加密内容或设备行为。'};
  }
  return {infer};
});
