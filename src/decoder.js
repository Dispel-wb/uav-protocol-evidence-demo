/* Byte-level decoder for demodulated MAVLink v1/v2 and SBUS captures.
   No RF demodulation, decryption, or MAVLink signature authentication. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ProtocolLab = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const MESSAGE = {
    0: { name: 'HEARTBEAT', crc: 50, min: 9 },
    24: { name: 'GPS_RAW_INT', crc: 24, min: 30 },
    30: { name: 'ATTITUDE', crc: 39, min: 28 },
    76: { name: 'COMMAND_LONG', crc: 152, min: 33 },
    77: { name: 'COMMAND_ACK', crc: 143, min: 3 },
  };
  const COMMAND = { 20: 'RETURN_TO_LAUNCH', 21: 'LAND', 22: 'TAKEOFF', 400: 'ARM_DISARM' };
  const ACK = { 0: 'ACCEPTED', 1: 'TEMPORARILY_REJECTED', 2: 'DENIED', 3: 'UNSUPPORTED', 4: 'FAILED', 5: 'IN_PROGRESS', 6: 'CANCELLED' };

  function parseHex(input) {
    const compact = String(input).replace(/0x/gi, '').replace(/[\s,;:_-]+/g, '');
    if (!compact) return new Uint8Array(0);
    if (!/^[0-9a-fA-F]+$/.test(compact)) throw new Error('十六进制输入包含非 0–9 / A–F 字符。');
    if (compact.length % 2) throw new Error('十六进制字符数必须为偶数。');
    return Uint8Array.from(compact.match(/../g), x => parseInt(x, 16));
  }
  function hex(bytes) { return Array.from(bytes, b => b.toString(16).padStart(2, '0').toUpperCase()).join(' '); }
  function crcX25(data, extra) {
    let crc = 0xffff;
    for (const byte of [...data, extra]) {
      let tmp = byte ^ (crc & 0xff);
      tmp ^= (tmp << 4) & 0xff;
      crc = (((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xffff);
    }
    return crc;
  }
  function view(bytes) { return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength); }
  function padded(bytes, n) { const out = new Uint8Array(n); out.set(bytes.slice(0, n)); return view(out); }
  function decodePayload(id, bytes) {
    const def = MESSAGE[id];
    if (!def || bytes.length < 1) return null;
    const v = padded(bytes, Math.max(bytes.length, 52));
    if (id === 0) return { customMode: v.getUint32(0, true), type: v.getUint8(4), autopilot: v.getUint8(5), baseMode: v.getUint8(6), armed: !!(v.getUint8(6) & 0x80), systemStatus: v.getUint8(7), mavlinkVersion: v.getUint8(8) };
    if (id === 24) return { latitude: v.getInt32(8, true) / 1e7, longitude: v.getInt32(12, true) / 1e7, altitudeM: v.getInt32(16, true) / 1000, fixType: v.getUint8(28), satellites: v.getUint8(29) };
    if (id === 30) return { rollDeg: v.getFloat32(4, true) * 180 / Math.PI, pitchDeg: v.getFloat32(8, true) * 180 / Math.PI, yawDeg: v.getFloat32(12, true) * 180 / Math.PI };
    if (id === 76) {
      const command = v.getUint16(28, true);
      return { command, commandName: COMMAND[command] || `MAV_CMD_${command}`, param1: v.getFloat32(0, true), param7: v.getFloat32(24, true), targetSystem: v.getUint8(30), targetComponent: v.getUint8(31), confirmation: v.getUint8(32) };
    }
    if (id === 77) {
      const command = v.getUint16(0, true), result = v.getUint8(2);
      return { command, commandName: COMMAND[command] || `MAV_CMD_${command}`, result, resultName: ACK[result] || `RESULT_${result}` };
    }
    return null;
  }
  function mavFrame(bytes, at) {
    const v2 = bytes[at] === 0xfd;
    const header = v2 ? 10 : 6;
    if (bytes.length - at < header) return { incomplete: true, expected: header, available: bytes.length - at };
    const len = bytes[at + 1], flags = v2 ? bytes[at + 2] : 0, signed = !!(flags & 1);
    const total = header + len + 2 + (signed ? 13 : 0);
    if (bytes.length - at < total) return { incomplete: true, expected: total, available: bytes.length - at };
    const packet = bytes.slice(at, at + total), id = v2 ? packet[7] | (packet[8] << 8) | (packet[9] << 16) : packet[5];
    const def = MESSAGE[id], payload = packet.slice(header, header + len), observed = packet[header + len] | (packet[header + len + 1] << 8);
    const computed = def ? crcX25(packet.slice(1, header + len), def.crc) : null;
    const crc = def ? (observed === computed ? 'valid' : 'invalid') : 'unknown-definition';
    return { family: v2 ? 'MAVLink 2' : 'MAVLink 1', offset: at, length: total, raw: hex(packet), messageId: id,
      name: def ? def.name : `MSG_${id}`, payloadLength: len, seq: packet[v2 ? 4 : 2], systemId: packet[v2 ? 5 : 3], componentId: packet[v2 ? 6 : 4],
      signed, signatureVerified: false, incompatibleFlags: flags & ~1, crc, observedCrc: observed, computedCrc: computed,
      fields: crc === 'invalid' ? null : decodePayload(id, payload),
      note: !def ? '本地字典未含此消息定义，不能验证 CRC_EXTRA 或解析字段。' : (!v2 && len < def.min ? 'MAVLink 1 载荷短于消息最小长度。' : '') };
  }
  function sbusFrame(bytes, at) {
    if (bytes.length - at < 25) return { incomplete: true, expected: 25, available: bytes.length - at };
    const packet = bytes.slice(at, at + 25);
    if ((packet[23] & 0xf0) !== 0 || ![0x00, 0x04].includes(packet[24])) return { rejected: true };
    const channels = [];
    for (let ch = 0; ch < 16; ch++) {
      const bit = ch * 11, pos = 1 + (bit >> 3), shift = bit & 7;
      const word = (packet[pos] || 0) | ((packet[pos + 1] || 0) << 8) | ((packet[pos + 2] || 0) << 16);
      channels.push((word >> shift) & 0x7ff);
    }
    const flags = packet[23];
    return { family: 'SBUS', offset: at, length: 25, raw: hex(packet), name: 'RC_CHANNELS', channels,
      frameLost: !!(flags & 4), failsafe: !!(flags & 8), digital17: !!(flags & 1), digital18: !!(flags & 2),
      endByte: packet[24], note: packet[24] !== 0 ? '结束字节非 00；请结合接收机实现核对。' : '' };
  }
  function scan(bytes) {
    const data = bytes instanceof Uint8Array ? bytes : Uint8Array.from(bytes);
    const frames = [], gaps = [];
    let i = 0, gapStart = -1;
    function closeGap(end) { if (gapStart >= 0) { gaps.push({ offset: gapStart, length: end - gapStart, raw: hex(data.slice(gapStart, end)) }); gapStart = -1; } }
    while (i < data.length) {
      const b = data[i];
      if (b !== 0xfd && b !== 0xfe && b !== 0x0f) { if (gapStart < 0) gapStart = i; i++; continue; }
      closeGap(i);
      const result = b === 0x0f ? sbusFrame(data, i) : mavFrame(data, i);
      if (result.rejected) { if (gapStart < 0) gapStart = i; i++; continue; }
      if (result.incomplete) { gaps.push({ offset: i, length: data.length - i, raw: hex(data.slice(i)), incomplete: true, expected: result.expected }); break; }
      frames.push(result); i += result.length;
    }
    closeGap(i);
    return { frames, gaps, bytes: data.length };
  }
  function analyze(bytes, rules = {}) {
    const settings = { maxAltitudeM: Number.isFinite(+rules.maxAltitudeM) ? +rules.maxAltitudeM : 120,
      requireArmAck: rules.requireArmAck !== false, minGpsFix: Number.isInteger(+rules.minGpsFix) ? +rules.minGpsFix : 3,
      sbusLostFrameLimit: Number.isInteger(+rules.sbusLostFrameLimit) ? +rules.sbusLostFrameLimit : 2 };
    const result = scan(bytes), findings = [], timeline = [];
    let armed = false, pendingArm = false, sbusLostStreak = 0, gpsFix = null;
    const lastSeq = new Map();
    function finding(frame, level, title, detail) { findings.push({ offset: frame.offset, family: frame.family, level, title, detail, evidence: frame.raw }); }
    for (const frame of result.frames) {
      const actions = [];
      if (frame.family.startsWith('MAVLink')) {
        if (frame.incompatibleFlags) finding(frame, 'error', '未知不兼容标志', `flags=0x${frame.incompatibleFlags.toString(16)}；该帧不应按已知定义使用。`);
        if (frame.crc === 'invalid') finding(frame, 'error', 'CRC 校验失败', `报文 CRC=0x${frame.observedCrc.toString(16)}，本地计算=0x${frame.computedCrc.toString(16)}。`);
        if (frame.crc === 'unknown-definition') finding(frame, 'info', '未知消息定义', frame.note);
        if (frame.signed) finding(frame, 'info', '签名未验', '检测到 MAVLink 2 签名段；本演示未持有密钥，不能确认来源。');
        if (frame.note && frame.crc !== 'unknown-definition') finding(frame, 'warning', '消息长度', frame.note);
        const key = `${frame.systemId}/${frame.componentId}`;
        if (frame.crc === 'valid' && lastSeq.has(key) && frame.seq !== ((lastSeq.get(key) + 1) & 255))
          finding(frame, 'warning', '序号跳变', `发送方 ${key} 前序号 ${lastSeq.get(key)}，当前 ${frame.seq}。`);
        if (frame.crc === 'valid') lastSeq.set(key, frame.seq);
        const f = frame.fields;
        if (frame.crc === 'valid' && !frame.incompatibleFlags && f) {
          if (frame.messageId === 0 && frame.componentId === 1) { armed = f.armed; actions.push(`飞控状态：${armed ? '已解锁' : '未解锁'}`); }
          if (frame.messageId === 24) { gpsFix = f.fixType; actions.push(`GPS fix=${gpsFix}`); }
          if (frame.messageId === 76) {
            actions.push(`命令 ${f.commandName}`);
            if (f.command === 400 && f.param1 >= 0.5) pendingArm = true;
            if (f.command === 22) {
              if (settings.requireArmAck && !armed) finding(frame, 'warning', '起飞前未确认解锁', '未见飞控 HEARTBEAT 已解锁或 ARM 命令的成功 ACK。');
              if (!Number.isFinite(f.param7) || f.param7 <= 0 || f.param7 > settings.maxAltitudeM)
                finding(frame, 'warning', '起飞高度超出配置范围', `目标高度 ${f.param7.toFixed(1)} m；当前上限 ${settings.maxAltitudeM} m。`);
              if (gpsFix !== null && gpsFix < settings.minGpsFix) finding(frame, 'warning', 'GPS 定位不足', `fix_type=${gpsFix}，要求至少 ${settings.minGpsFix}。`);
            }
          }
          if (frame.messageId === 77) {
            actions.push(`${f.commandName} → ${f.resultName}`);
            if (f.command === 400 && pendingArm) {
              if (f.result === 0) armed = true;
              pendingArm = false;
            }
            if (f.result !== 0 && f.result !== 5) finding(frame, 'warning', '命令未获接受', `${f.commandName} 返回 ${f.resultName}。`);
          }
        }
      } else {
        sbusLostStreak = frame.frameLost ? sbusLostStreak + 1 : 0;
        actions.push(`通道 1–4: ${frame.channels.slice(0, 4).join(' / ')}`);
        if (frame.failsafe) finding(frame, 'error', 'SBUS failsafe', '接收机标记失控保护；该帧不能当作有效人工控制输入。');
        else if (frame.frameLost && sbusLostStreak >= settings.sbusLostFrameLimit)
          finding(frame, 'warning', '连续丢帧', `已连续 ${sbusLostStreak} 帧标记 frame lost；这不等同于 failsafe。`);
        if (frame.note) finding(frame, 'info', '结束字节', frame.note);
      }
      timeline.push({ offset: frame.offset, family: frame.family, name: frame.name, status: findings.some(x => x.offset === frame.offset) ? 'review' : (frame.crc === 'valid' || frame.family === 'SBUS' ? 'ok' : 'unknown'), actions });
    }
    for (const gap of result.gaps) findings.push({ offset: gap.offset, family: '未知字节', level: gap.incomplete ? 'warning' : 'info', title: gap.incomplete ? '截断帧' : '未识别字节', detail: gap.incomplete ? `需要至少 ${gap.expected} 字节，当前仅剩 ${gap.length} 字节。` : `有 ${gap.length} 字节未匹配 MAVLink 或 SBUS 帧头。`, evidence: gap.raw });
    return { ...result, timeline, findings, rules: settings, summary: { totalBytes: result.bytes, frames: result.frames.length, mavlink: result.frames.filter(x => x.family.startsWith('MAVLink')).length, sbus: result.frames.filter(x => x.family === 'SBUS').length, findings: findings.length } };
  }
  return { parseHex, hex, crcX25, mavFrame, sbusFrame, scan, analyze, MESSAGE };
});
