/* Stateful analysis for timestamped chunks of already-demodulated bytes.
   The retained sliding window lets frames split across chunks be recovered. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.StreamIntelligence = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function append(left, right, limit) {
    const joined = new Uint8Array(left.length + right.length);
    joined.set(left); joined.set(right, left.length);
    return joined.length > limit ? joined.slice(joined.length - limit) : joined;
  }

  function create(dependencies, options = {}) {
    const { decoder, discovery, intelligence } = dependencies || {};
    if (!decoder || !discovery || !intelligence) throw new Error('需要 decoder、discovery 和 intelligence 三个分析模块。');
    const windowBytes = Number.isInteger(options.windowBytes) && options.windowBytes > 0 ? options.windowBytes : 65536;
    let window = new Uint8Array(0), previousFamilies = new Set(), previousTimestamp = null;
    let chunkCount = 0, totalBytes = 0, droppedChunks = 0;

    function push(chunk) {
      if (!chunk || !Number.isFinite(chunk.timestampMs)) throw new Error('数据块必须包含有限的 timestampMs。');
      if (previousTimestamp !== null && chunk.timestampMs < previousTimestamp) throw new Error('timestampMs 必须单调不减。');
      const bytes = chunk.bytes instanceof Uint8Array ? chunk.bytes : Uint8Array.from(chunk.bytes || []);
      if (!bytes.length) throw new Error('数据块 bytes 不能为空。');
      const intervalMs = previousTimestamp === null ? null : chunk.timestampMs - previousTimestamp;
      window = append(window, bytes, windowBytes);
      chunkCount++; totalBytes += bytes.length;
      if (chunk.dropped) droppedChunks++;

      const parsed = decoder.analyze(window, chunk.rules || {});
      const inferred = discovery.infer(window, parsed.gaps);
      const link = intelligence.assess(window, parsed, inferred);
      const currentFamilies = new Set(link.composition.map(item => item.family));
      const appeared = [...currentFamilies].filter(name => !previousFamilies.has(name));
      const disappeared = [...previousFamilies].filter(name => !currentFamilies.has(name));
      previousFamilies = currentFamilies;
      previousTimestamp = chunk.timestampMs;

      return {
        schema: 'capture-window-v1',
        source: chunk.source || 'unspecified',
        timestampMs: chunk.timestampMs,
        chunk: { index: chunkCount, bytes: bytes.length, dropped: !!chunk.dropped },
        stream: {
          totalBytes,
          retainedBytes: window.length,
          intervalMs,
          instantaneousBytesPerSecond: intervalMs > 0 ? Math.round(bytes.length * 1000 / intervalMs) : null,
          droppedChunks,
        },
        changes: { appeared, disappeared, changed: appeared.length > 0 || disappeared.length > 0 },
        parsed,
        discovery: inferred,
        linkAssessment: link,
      };
    }

    function reset() {
      window = new Uint8Array(0); previousFamilies = new Set(); previousTimestamp = null;
      chunkCount = 0; totalBytes = 0; droppedChunks = 0;
    }

    return { push, reset, schema: 'capture-chunk-v1' };
  }

  return { create };
});
