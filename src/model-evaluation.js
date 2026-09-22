/* Open-set evaluation and threshold calibration for protocol-family models. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ModelEvaluation = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function metrics(records) {
    const known = records.filter(record => record.truth !== 'unknown');
    const unknown = records.filter(record => record.truth === 'unknown');
    const correctKnown = known.filter(record => record.prediction === record.truth).length;
    const rejectedKnown = known.filter(record => record.prediction === 'unknown').length;
    const rejectedUnknown = unknown.filter(record => record.prediction === 'unknown').length;
    const falseAcceptedUnknown = unknown.length - rejectedUnknown;
    const round = value => Math.round(value * 1000) / 1000;
    return {
      total: records.length,
      known: known.length,
      unknown: unknown.length,
      knownAccuracy: known.length ? round(correctKnown / known.length) : null,
      falseRejectRate: known.length ? round(rejectedKnown / known.length) : null,
      unknownRecall: unknown.length ? round(rejectedUnknown / unknown.length) : null,
      falseAcceptRate: unknown.length ? round(falseAcceptedUnknown / unknown.length) : null,
      meanLatencyMs: records.some(record => Number.isFinite(record.latencyMs)) ? round(records.filter(record => Number.isFinite(record.latencyMs)).reduce((sum, record) => sum + record.latencyMs, 0) / records.filter(record => Number.isFinite(record.latencyMs)).length) : null,
    };
  }

  function calibrate(modelApi, model, validation, options = {}) {
    if (!validation.some(item => item.label === 'unknown')) throw new Error('校准集必须包含未知协议样本。');
    if (!validation.some(item => item.label !== 'unknown')) throw new Error('校准集必须包含已知协议样本。');
    const scoreThresholds = options.scoreThresholds || [0.4, 0.5, 0.58, 0.65, 0.72, 0.8];
    const marginThresholds = options.marginThresholds || [0, 0.02, 0.04, 0.08, 0.12, 0.18];
    const scored = validation.map(item => ({ item, raw: modelApi.score(model, item.bytes) }));
    const candidates = [];
    for (const threshold of scoreThresholds) {
      for (const marginThreshold of marginThresholds) {
        const records = scored.map(({ item, raw }) => ({
          truth: item.label,
          prediction: raw.score >= threshold && raw.margin >= marginThreshold ? raw.topLabel : 'unknown',
        }));
        const result = metrics(records);
        const balanced = ((result.knownAccuracy || 0) + (result.unknownRecall || 0)) / 2;
        candidates.push({ threshold, marginThreshold, balanced, metrics: result });
      }
    }
    candidates.sort((a, b) => b.balanced - a.balanced || a.metrics.falseAcceptRate - b.metrics.falseAcceptRate || a.threshold - b.threshold || a.marginThreshold - b.marginThreshold);
    const best = candidates[0];
    return { schema: 'open-set-calibration-v1', threshold: best.threshold, marginThreshold: best.marginThreshold, balancedScore: Math.round(best.balanced * 1000) / 1000, metrics: best.metrics, evaluatedCandidates: candidates.length };
  }

  function evaluate(modelApi, model, examples, thresholds) {
    const records = examples.map(item => {
      const started = typeof performance !== 'undefined' ? performance.now() : Date.now();
      const result = modelApi.predict(model, item.bytes, thresholds);
      const ended = typeof performance !== 'undefined' ? performance.now() : Date.now();
      return { id: item.id, group: item.group, truth: item.label, prediction: result.label, score: result.score, margin: result.margin, latencyMs: ended - started };
    });
    return { schema: 'open-set-evaluation-v1', metrics: metrics(records), records };
  }

  return { metrics, calibrate, evaluate };
});
