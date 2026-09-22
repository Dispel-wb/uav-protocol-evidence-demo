/* Capture-level link assessment built on parser and discovery evidence.
   It does not infer RF quality because the input contains bytes, not IQ samples. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.LinkIntelligence = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const round1 = value => Math.round(value * 10) / 10;

  function entropy(bytes) {
    if (!bytes.length) return 0;
    const counts = new Uint32Array(256);
    for (const value of bytes) counts[value]++;
    let result = 0;
    for (const count of counts) {
      if (!count) continue;
      const probability = count / bytes.length;
      result -= probability * Math.log2(probability);
    }
    return round1(result);
  }

  function assess(input, parsed, discovered) {
    const bytes = input instanceof Uint8Array ? input : Uint8Array.from(input || []);
    const frames = parsed.frames || [];
    const families = discovered.families || [];
    const ownership = new Uint8Array(bytes.length); // 0 unexplained, 1 known, 2 inferred
    const segments = [];

    for (const frame of frames) {
      ownership.fill(1, frame.offset, Math.min(bytes.length, frame.offset + frame.length));
      segments.push({ offset: frame.offset, length: frame.length, family: frame.family, kind: 'known' });
    }
    for (const family of families) {
      for (const packet of family.packets) {
        for (let at = packet.offset; at < Math.min(bytes.length, packet.offset + packet.length); at++) {
          if (!ownership[at]) ownership[at] = 2;
        }
        segments.push({ offset: packet.offset, length: packet.length, family: family.id, kind: 'inferred' });
      }
    }
    segments.sort((a, b) => a.offset - b.offset || b.length - a.length);

    let knownBytes = 0, inferredBytes = 0;
    for (const value of ownership) {
      if (value === 1) knownBytes++;
      else if (value === 2) inferredBytes++;
    }
    const unexplainedBytes = Math.max(0, bytes.length - knownBytes - inferredBytes);
    const validFrames = frames.filter(frame => frame.family === 'SBUS' || frame.crc === 'valid').length;
    const protocolNames = [...new Set(segments.map(segment => segment.family))];
    let transitions = 0;
    for (let at = 1; at < segments.length; at++) {
      if (segments[at].family !== segments[at - 1].family) transitions++;
    }

    const mavEndpoints = [...new Set(frames.filter(frame => frame.family.startsWith('MAVLink')).map(frame => `${frame.systemId}/${frame.componentId}`))];
    const severity = { error: 0, warning: 0, info: 0 };
    for (const finding of parsed.findings || []) {
      if (severity[finding.level] !== undefined) severity[finding.level]++;
    }

    const total = bytes.length || 1;
    const coveragePercent = round1((knownBytes + inferredBytes) / total * 100);
    const knownPercent = round1(knownBytes / total * 100);
    const integrityPercent = frames.length ? round1(validFrames / frames.length * 100) : null;
    const verifiedUnknownFamilies = families.filter(family => !!family.checksum).length;

    let classification = '证据不足';
    if (knownPercent >= 90 && (integrityPercent === null || integrityPercent >= 90)) classification = '已知协议链路';
    else if (coveragePercent >= 80 && knownBytes > 0 && families.length) classification = '已知与未知结构混合链路';
    else if (coveragePercent >= 80 && families.length) classification = '未知结构候选链路';
    else if (coveragePercent >= 80) classification = '已分段链路';
    else if (families.length) classification = '未知结构候选链路';

    let confidence = '低';
    if (coveragePercent >= 95 && unexplainedBytes === 0 && (!families.length || verifiedUnknownFamilies === families.length)) confidence = '高';
    else if (coveragePercent >= 70 && (frames.length || families.length)) confidence = '中';

    const nextActions = [];
    if (unexplainedBytes) nextActions.push(`补充重复捕获或已知操作标签，解释剩余 ${unexplainedBytes} 字节。`);
    if (families.some(family => !family.checksum)) nextActions.push('为低置信度未知族采集更多帧，验证边界与校验假设。');
    if (frames.some(frame => frame.crc === 'invalid')) nextActions.push('检查传输损坏、字节边界或协议版本，复核 CRC 失败帧。');
    if (transitions) nextActions.push(`按 ${transitions} 个协议切换点检查复用、转发或拼接关系。`);
    if (!nextActions.length) nextActions.push('保存本次结果作为回归基线，并用独立捕获验证。');

    return {
      schema: 'link-assessment-v1',
      classification,
      confidence,
      metrics: {
        totalBytes: bytes.length,
        knownBytes,
        inferredBytes,
        unexplainedBytes,
        coveragePercent,
        knownPercent,
        integrityPercent,
        byteEntropy: entropy(bytes),
        protocolCount: protocolNames.length,
        transitions,
      },
      composition: protocolNames.map(name => ({
        family: name,
        frames: segments.filter(segment => segment.family === name).length,
        bytes: segments.filter(segment => segment.family === name).reduce((sum, segment) => sum + segment.length, 0),
        evidence: segments.some(segment => segment.family === name && segment.kind === 'inferred') ? '结构推断' : '协议解析',
      })),
      sessions: { mavEndpoints, sbusFrames: frames.filter(frame => frame.family === 'SBUS').length, unknownFamilies: families.length },
      severity,
      nextActions,
      boundary: '本评估只描述解调后字节的协议覆盖、完整性和组成；不能据此估计射频 SNR、误码率、调制方式或频偏。',
    };
  }

  return { entropy, assess };
});
