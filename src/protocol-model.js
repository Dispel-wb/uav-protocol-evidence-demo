/* Small, explainable protocol-family baseline for demodulated frame bytes.
   This is a research baseline, not a claim of general protocol recognition. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ProtocolModel = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function normalize(values) {
    const norm = Math.sqrt(values.reduce((sum, value) => sum + value * value, 0));
    return norm ? values.map(value => value / norm) : values;
  }

  function features(input) {
    const bytes = input instanceof Uint8Array ? input : Uint8Array.from(input || []);
    if (!bytes.length) throw new Error('特征输入不能为空。');
    const histogram = Array(256).fill(0), bigrams = Array(64).fill(0);
    for (const byte of bytes) histogram[byte]++;
    for (let at = 1; at < bytes.length; at++) bigrams[(bytes[at - 1] * 31 + bytes[at]) & 63]++;
    const vector = [Math.min(bytes.length, 256) / 256, ...histogram.map(count => count / bytes.length), ...bigrams.map(count => count / Math.max(1, bytes.length - 1))];
    return normalize(vector);
  }

  function similarity(left, right) {
    return left.reduce((sum, value, index) => sum + value * right[index], 0);
  }

  function train(examples) {
    if (!Array.isArray(examples) || examples.length < 2) throw new Error('至少需要两个带标签训练样本。');
    const grouped = new Map();
    for (const example of examples) {
      if (!example.label) throw new Error('每个训练样本必须有 label。');
      const vector = features(example.bytes);
      if (!grouped.has(example.label)) grouped.set(example.label, []);
      grouped.get(example.label).push(vector);
    }
    if (grouped.size < 2) throw new Error('至少需要两个协议类别。');
    const centroids = {};
    for (const [label, vectors] of grouped) {
      const mean = Array(vectors[0].length).fill(0);
      for (const vector of vectors) vector.forEach((value, index) => { mean[index] += value / vectors.length; });
      centroids[label] = normalize(mean);
    }
    return { schema: 'protocol-centroid-v1', labels: [...grouped.keys()], centroids, counts: Object.fromEntries([...grouped].map(([label, values]) => [label, values.length])) };
  }

  function predict(model, input, options = {}) {
    if (!model || model.schema !== 'protocol-centroid-v1') throw new Error('模型格式无效。');
    const threshold = Number.isFinite(options.threshold) ? options.threshold : 0.58;
    const marginThreshold = Number.isFinite(options.marginThreshold) ? options.marginThreshold : 0.04;
    const vector = features(input);
    const scores = model.labels.map(label => ({ label, score: similarity(vector, model.centroids[label]) })).sort((a, b) => b.score - a.score);
    const margin = scores[0].score - (scores[1]?.score || 0);
    const accepted = scores[0].score >= threshold && margin >= marginThreshold;
    return {
      label: accepted ? scores[0].label : 'unknown',
      accepted,
      score: Math.round(scores[0].score * 1000) / 1000,
      margin: Math.round(margin * 1000) / 1000,
      scores: scores.map(item => ({ label: item.label, score: Math.round(item.score * 1000) / 1000 })),
      reason: accepted ? '最高相似度和类别间隔均达到阈值。' : '相似度或类别间隔不足，执行开集拒识。',
    };
  }

  return { features, train, predict };
});
