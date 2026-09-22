/* Conservative next-capture recommendations and controlled before/after diffs. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ActiveLearning = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const parseRaw = raw => Uint8Array.from(String(raw).split(/\s+/).filter(Boolean).map(value => parseInt(value, 16)));

  function recommend(context) {
    const discovery = context.discovery || { families: [], unexplainedBytes: 0 };
    const state = context.stateAnalysis || { violations: [] };
    const actions = [];
    for (const family of discovery.families) {
      if (!family.checksum) actions.push({ priority: 1, family: family.id, action: '保持设备状态不变，再采集至少5帧。', reason: '当前只有重复结构，尚无一致校验依据。', acceptance: '候选帧边界稳定，并出现可重复校验或明确否定现有假设。' });
      if (family.columns.some(column => column.label === '候选类型')) actions.push({ priority: 2, family: family.id, action: '每次只改变一个设备操作，分别采集操作前后数据。', reason: '存在候选类型字段，需要受控变量确定其与操作的关系。', acceptance: '同一偏移在组内稳定、组间变化，且能在独立重复实验中复现。' });
      if (family.columns.some(column => column.label === '候选序号')) actions.push({ priority: 3, family: family.id, action: '保持空闲状态连续采集，再重复一次相同命令。', reason: '用于区分自然递增序号和由命令触发的字段。', acceptance: '序号在空闲和操作阶段均按同一规律递增。' });
    }
    if (discovery.unexplainedBytes) actions.push({ priority: 1, family: '未解释字节', action: '扩大捕获时长，并记录每次人工操作的时间点。', reason: `仍有 ${discovery.unexplainedBytes} 字节缺少重复证据。`, acceptance: '至少形成3个可对齐重复片段，或证明其为噪声/截断数据。' });
    if (state.violations.some(item => item.type === 'missing-ack' || item.type === 'precondition')) actions.push({ priority: 1, family: '会话状态', action: '从心跳开始捕获完整的命令前、命令和应答阶段。', reason: '当前会话缺少前置状态或后续应答。', acceptance: '同一捕获中形成状态证据、命令和对应应答的完整因果链。' });
    if (!actions.length) actions.push({ priority: 3, family: '回归验证', action: '更换设备或协议版本，重复同一任务。', reason: '当前捕获内证据闭环，需要验证跨设备与跨版本复用。', acceptance: '独立捕获保持解析、状态和规则结论一致，或明确记录版本漂移。' });
    const merged = new Map();
    for (const item of actions) {
      const key = `${item.action}|${item.reason}|${item.acceptance}`;
      if (!merged.has(key)) merged.set(key, { ...item });
      else merged.get(key).family = `${merged.get(key).family}、${item.family}`;
    }
    return [...merged.values()].sort((a, b) => a.priority - b.priority);
  }

  function controlledDiff(beforePackets, afterPackets) {
    const before = beforePackets.map(packet => packet instanceof Uint8Array ? packet : parseRaw(packet.raw || packet));
    const after = afterPackets.map(packet => packet instanceof Uint8Array ? packet : parseRaw(packet.raw || packet));
    if (before.length < 2 || after.length < 2) throw new Error('操作前后各至少需要2帧，才能区分组内波动和组间变化。');
    const width = Math.min(...[...before, ...after].map(packet => packet.length));
    const candidates = [];
    for (let offset = 0; offset < width; offset++) {
      const left = [...new Set(before.map(packet => packet[offset]))];
      const right = [...new Set(after.map(packet => packet[offset]))];
      if (left.length === 1 && right.length === 1 && left[0] !== right[0]) candidates.push({ offset, before: left[0], after: right[0], evidence: '操作前后组内稳定且组间改变' });
    }
    return { schema: 'controlled-diff-v1', beforeCount: before.length, afterCount: after.length, comparedBytes: width, candidates };
  }

  function propose(candidate, evidence) {
    return { schema: 'knowledge-candidate-v1', status: 'candidate', candidate, evidence, createdAt: new Date().toISOString() };
  }
  function approve(record, reviewer) {
    if (!record || record.status !== 'candidate') throw new Error('只能确认候选知识。');
    if (!reviewer) throw new Error('确认人不能为空。');
    return { ...record, status: 'approved', approvedBy: reviewer, approvedAt: new Date().toISOString() };
  }
  function appendApprovedExample(examples, record) {
    if (!record || record.status !== 'approved') throw new Error('未经人工确认的候选不能进入训练集。');
    if (!record.candidate?.label || !record.candidate?.bytes) throw new Error('候选训练样本必须包含 label 和 bytes。');
    return [...examples, { label: record.candidate.label, bytes: record.candidate.bytes, evidence: record.evidence, approvedBy: record.approvedBy }];
  }

  return { recommend, controlledDiff, propose, approve, appendApprovedExample };
});
