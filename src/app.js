(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const decoder = window.ProtocolLab;
  const discovery = window.ProtocolDiscovery;
  const samples = window.ProtocolSamples;
  let report = null, currentBytes = null;
  let rules = { maxAltitudeM: 120, minGpsFix: 3, sbusLostFrameLimit: 2, requireArmAck: true };
  const safe = v => String(v).replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const fmt = n => Number(n).toLocaleString('zh-CN');

  function loadRules() {
    try { const saved = JSON.parse(localStorage.getItem('protocol-lab-rules') || 'null'); if (saved) rules = { ...rules, ...saved }; } catch (_) {}
    $('max-altitude').value = rules.maxAltitudeM;
    $('min-gps').value = rules.minGpsFix;
    $('lost-limit').value = rules.sbusLostFrameLimit;
    $('require-arm').checked = rules.requireArmAck;
  }
  function readRules() {
    const maxAltitudeM = Number($('max-altitude').value), minGpsFix = Number($('min-gps').value), sbusLostFrameLimit = Number($('lost-limit').value);
    if (!Number.isFinite(maxAltitudeM) || maxAltitudeM < 1 || maxAltitudeM > 10000) throw new Error('起飞高度上限须为 1–10000 m。');
    if (!Number.isInteger(sbusLostFrameLimit) || sbusLostFrameLimit < 1 || sbusLostFrameLimit > 50) throw new Error('连续丢帧阈值须为 1–50。');
    return { maxAltitudeM, minGpsFix, sbusLostFrameLimit, requireArmAck: $('require-arm').checked };
  }
  function setSample(id) {
    const sample = samples.find(s => s.id === id);
    if (!sample) return;
    $('hex-input').value = sample.hex;
    $('sample').value = id;
    $('input-error').textContent = '';
    updateInputLength();
    analyze();
  }
  function updateInputLength() {
    try { $('input-length').textContent = `${fmt(decoder.parseHex($('hex-input').value).length)} 字节`; }
    catch (_) { $('input-length').textContent = '格式待修正'; }
  }
  function analyze() {
    try {
      currentBytes = decoder.parseHex($('hex-input').value);
      if (!currentBytes.length) throw new Error('请粘贴解调后的十六进制字节，或选择内置样本。');
      report = decoder.analyze(currentBytes, rules);
      report.discovery = discovery.infer(currentBytes, report.gaps);
      report.findings = report.findings.filter(f => f.title !== '未识别字节');
      for (const gap of report.discovery.unexplained) report.findings.push({offset:gap.offset,family:'未知字节',level:'info',title:'结构尚未推断',detail:`${gap.length} 字节缺少足够重复证据。`,evidence:gap.raw});
      report.summary.findings = report.findings.length;
      $('input-error').textContent = '';
      render();
    } catch (e) {
      $('input-error').textContent = e.message;
      $('parse-status').textContent = '输入未完成解析';
      report = null;
      $('download').disabled = true;
    }
  }
  function frameStatus(frame) {
    if (frame.discovery) return ['unknown', '结构候选'];
    const own = report.findings.some(x => x.offset === frame.offset);
    if (own) return ['review', '待复核'];
    if (frame.family === 'SBUS' || frame.crc === 'valid') return ['', '已解析'];
    return ['unknown', '待定义'];
  }
  function integrity(frame) {
    if (frame.discovery) return frame.checksum ? `${frame.checksum} 候选 ✓` : '无校验依据';
    if (frame.family === 'SBUS') return '帧边界 / 无 CRC';
    if (frame.crc === 'valid') return frame.signed ? 'CRC ✓ / 签名未验' : 'CRC ✓';
    if (frame.crc === 'invalid') return 'CRC ×';
    return 'CRC_EXTRA 未知';
  }
  function description(frame) {
    if (frame.discovery) return `前缀 ${frame.magic.match(/../g).join(' ')} · 长度字段 +${frame.lengthOffset}`;
    const f = frame.fields;
    if (frame.family === 'SBUS') return `CH1–4 ${frame.channels.slice(0,4).join(' / ')}`;
    if (!f) return frame.note || '原始载荷保留';
    if (frame.messageId === 0) return `${f.armed ? '已解锁' : '未解锁'} · status ${f.systemStatus}`;
    if (frame.messageId === 24) return `fix ${f.fixType} · ${f.satellites} 星`;
    if (frame.messageId === 30) return `yaw ${f.yawDeg.toFixed(1)}°`;
    if (frame.messageId === 76) return `${f.commandName} · param7 ${f.param7.toFixed(1)}`;
    if (frame.messageId === 77) return `${f.commandName} · ${f.resultName}`;
    return '字段已解析';
  }
  function renderStream() {
    const all = [];
    let cursor = 0;
    for (const frame of displayFrames()) {
      if (frame.offset > cursor) all.push({offset:cursor,length:frame.offset-cursor,segmentType:'gap'});
      all.push({...frame,segmentType:'frame'});
      cursor = frame.offset + frame.length;
    }
    if (cursor < report.bytes) all.push({offset:cursor,length:report.bytes-cursor,segmentType:'gap'});
    const track = all.map(x => {
      const percent = Math.max(4, x.length / report.bytes * 100);
      const cls = x.segmentType === 'gap' ? 'gap' : x.discovery ? 'inferred' : x.family === 'SBUS' ? 'sbus' : x.crc === 'invalid' ? 'error' : '';
      const title = x.segmentType === 'gap' ? `未识别 ${x.length} B` : `${x.family} · ${x.name} · ${x.length} B`;
      const shortName = x.segmentType === 'gap' ? '…' : x.discovery ? x.family : x.family === 'SBUS' ? 'SBUS' : ({HEARTBEAT:'HB',GPS_RAW_INT:'GPS',ATTITUDE:'ATT',COMMAND_LONG:'CMD',COMMAND_ACK:'ACK'}[x.name] || `#${x.messageId}`);
      return `<div class="segment ${cls}" style="flex:${x.length} 1 0;max-width:${Math.max(percent,7)}%" title="${safe(title)}">${safe(shortName)}</div>`;
    }).join('');
    $('stream').innerHTML = `<div class="stream-caption">字节分段 · 按偏移排列（总长 ${fmt(report.bytes)} B）</div><div class="stream-track">${track}</div><div class="stream-legend"><span><i></i>MAVLink</span><span><i class="s"></i>SBUS</span><span><i class="u"></i>未知结构候选</span><span><i class="e"></i>校验错误</span></div>`;
  }
  function displayFrames() {
    const inferred = report.discovery.families.flatMap(family => family.packets.map(p => ({...p, discovery:true, family:family.id, name:'未知报文', magic:family.magic, lengthOffset:family.lengthOffset, checksum:family.checksum, columns:family.columns, confidence:family.confidence})));
    return [...report.frames,...inferred].sort((a,b)=>a.offset-b.offset);
  }
  function showFrame(index) {
    const frame = displayFrames()[index];
    if (!frame) return;
    document.querySelectorAll('#frame-rows tr').forEach((tr,i) => tr.classList.toggle('selected', i === index));
    const fields = frame.discovery ? { structureConfidence:frame.confidence, candidateFields:frame.columns.map(c=>`${typeof c.offset === 'number' ? '+'+c.offset : c.offset} ${c.label}：${c.evidence}`).join('；') } : frame.family === 'SBUS' ? { channelsRaw: frame.channels, frameLost: frame.frameLost, failsafe: frame.failsafe, digital17: frame.digital17, digital18: frame.digital18 } : (frame.fields || {});
    const dl = Object.entries(fields).map(([k,v]) => `<dt>${safe(k)}</dt><dd>${safe(typeof v === 'number' && !Number.isInteger(v) ? +v.toFixed(5) : v)}</dd>`).join('');
    $('frame-detail').innerHTML = `<div class="detail-grid"><div><strong>${safe(frame.family)} · ${safe(frame.name)}</strong><dl><dt>起始偏移</dt><dd>${frame.offset} B</dd><dt>帧长</dt><dd>${frame.length} B</dd><dt>完整性</dt><dd>${safe(integrity(frame))}</dd>${frame.systemId !== undefined ? `<dt>来源</dt><dd>sys ${frame.systemId} / comp ${frame.componentId}</dd>` : ''}</dl></div><div><strong>解析字段</strong><dl>${dl || '<dd>该帧仅保留原始载荷。</dd>'}</dl></div></div><div class="raw" aria-label="原始帧字节">${safe(frame.raw)}</div>`;
  }
  function render() {
    const s = report.summary;
    const frames = displayFrames();
    $('m-bytes').textContent = fmt(s.totalBytes); $('m-frames').textContent = frames.length;
    $('m-mav').textContent = s.mavlink; $('m-sbus').textContent = s.sbus; $('m-findings').textContent = s.findings;
    $('parse-status').textContent = `${s.frames} 帧已知 · ${report.discovery.families.length} 族未知结构`;
    renderStream();
    $('frame-rows').innerHTML = frames.map((f,i) => {
      const [cls,status] = frameStatus(f);
      return `<tr data-index="${i}" tabindex="0"><td><code>+${f.offset}</code></td><td>${safe(f.family)}</td><td><strong>${safe(f.name)}</strong>${f.seq !== undefined ? `<br><code>seq ${f.seq} · ${f.payloadLength} B</code>` : ''}</td><td>${safe(integrity(f))}</td><td>${safe(description(f))}</td><td><span class="status ${cls}">${status}</span></td></tr>`;
    }).join('') || '<tr><td colspan="6" class="muted">未识别到完整帧。</td></tr>';
    $('frame-rows').querySelectorAll('tr[data-index]').forEach(tr => {
      const open = () => showFrame(+tr.dataset.index);
      tr.addEventListener('click', open);
      tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    });
    $('frame-detail').innerHTML = '<span class="muted">点击上方任意帧，查看其原始字节与解析字段。</span>';
    if (frames.length) showFrame(0);
    $('discovery-count').textContent = `${report.discovery.families.length} 族`;
    $('discovery').innerHTML = report.discovery.families.length ? report.discovery.families.map(f => `<article class="discovered"><div class="discovered-head"><strong>${safe(f.id)}</strong><span>${f.packetCount} 帧 · ${safe(f.confidence)}</span></div><p>${f.observations.map(safe).join('；')}。</p><div class="field-list">${f.columns.map(c => `<span><b>${typeof c.offset === 'number' ? '+'+c.offset : c.offset}</b> ${safe(c.label)}<small>${safe(c.evidence)}</small></span>`).join('')}</div><p class="discovery-note">各帧起始偏移：${f.packets.map(p=>`+${p.offset}`).join('、')} B。字段名称均为候选，需结合设备操作和更多捕获数据验证。</p></article>`).join('') : `<div class="empty">未形成可重复的未知帧结构。${safe(report.discovery.minimumEvidence)}剩余 ${report.discovery.unexplainedBytes} 字节。</div>`;
    $('finding-count').textContent = `${s.findings} 项`;
    $('findings').innerHTML = report.findings.length ? report.findings.map(f => `<div class="finding ${safe(f.level)}"><strong>${safe(f.title)} · +${f.offset} B</strong><div>${safe(f.detail)}</div><span>${safe(f.family)} · 原始证据：</span> <code>${safe(f.evidence.slice(0,100))}${f.evidence.length>100?' …':''}</code></div>`).join('') : '<div class="empty">当前规则范围内未发现待复核项。此结论不覆盖未收录的消息定义或射频链路。</div>';
    $('download').disabled = false;
  }
  function applyRules() {
    try {
      rules = readRules();
      try { localStorage.setItem('protocol-lab-rules', JSON.stringify(rules)); } catch (_) {}
      $('rules-status').classList.add('saved');
      $('rules-status').textContent = '条件已保存；已用新条件重跑当前字节流。';
      analyze();
    } catch (e) { $('rules-status').classList.remove('saved'); $('rules-status').textContent = e.message; }
  }
  async function importFile(file) {
    if (!file) return;
    try {
      if (/\.(hex|txt)$/i.test(file.name)) $('hex-input').value = await file.text();
      else $('hex-input').value = decoder.hex(new Uint8Array(await file.arrayBuffer()));
      $('sample').value = 'custom';
      updateInputLength(); analyze();
    } catch (e) { $('input-error').textContent = `导入失败：${e.message}`; }
  }
  function download() {
    if (!report) return;
    const payload = { schema:'protocol-lab-report-v2', generatedAt:new Date().toISOString(), inputHex:decoder.hex(currentBytes), ...report };
    const a = document.createElement('a'), url = URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    a.href = url; a.download = '谱航智析_字节流证据报告.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
  }

  $('sample').innerHTML = samples.map(x => `<option value="${safe(x.id)}">${safe(x.title)}</option>`).join('') + '<option value="custom">自定义字节流</option>';
  loadRules();
  $('sample').addEventListener('change', e => { if (e.target.value !== 'custom') setSample(e.target.value); });
  $('hex-input').addEventListener('input', () => { $('sample').value = 'custom'; updateInputLength(); });
  $('analyze').addEventListener('click', analyze);
  $('apply-rules').addEventListener('click', applyRules);
  $('reset-rules').addEventListener('click', () => { rules = {maxAltitudeM:120,minGpsFix:3,sbusLostFrameLimit:2,requireArmAck:true}; try{localStorage.removeItem('protocol-lab-rules')}catch(_){} loadRules(); applyRules(); });
  $('file-input').addEventListener('change', e => importFile(e.target.files[0]));
  $('download').addEventListener('click', download);
  setSample(samples[0].id);
})();
