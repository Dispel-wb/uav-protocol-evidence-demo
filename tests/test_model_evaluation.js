const assert = require('node:assert/strict');
const samples = require('../samples/catalog.json');
const decoder = require('../src/decoder');
const discovery = require('../src/discovery');
const modelApi = require('../src/protocol-model');
const evaluation = require('../src/model-evaluation');
const fixture = id => decoder.parseHex(samples.find(sample => sample.id === id).hex);
const frames = id => decoder.scan(fixture(id)).frames.map((frame, index) => ({ id: `${id}-${index}`, bytes: decoder.parseHex(frame.raw) }));

const training = [
  ...frames('mavlink2-normal').map(item => ({ ...item, label: 'MAVLink', group: 'mavlink-normal' })),
  ...frames('sbus-healthy').map(item => ({ ...item, label: 'SBUS', group: 'sbus-healthy' })),
];
const validation = [
  ...frames('mavlink2-anomaly').map(item => ({ ...item, label: 'MAVLink', group: 'mavlink-anomaly' })),
  ...frames('sbus-failsafe').map(item => ({ ...item, label: 'SBUS', group: 'sbus-failsafe' })),
];
const unknownBytes = fixture('unknown-two-families');
const inferred = discovery.infer(unknownBytes, [{ offset: 0, length: unknownBytes.length }]);
for (const [familyIndex, family] of inferred.families.entries()) {
  family.packets.forEach((packet, index) => validation.push({ id: `unknown-${familyIndex}-${index}`, label: 'unknown', group: `unknown-family-${familyIndex}`, bytes: unknownBytes.slice(packet.offset, packet.offset + packet.length) }));
}

const model = modelApi.train(training);
const calibrated = evaluation.calibrate(modelApi, model, validation);
assert.equal(calibrated.schema, 'open-set-calibration-v1');
assert.equal(calibrated.evaluatedCandidates, 36);
const report = evaluation.evaluate(modelApi, model, validation, calibrated);
assert.equal(report.metrics.knownAccuracy, 1);
assert.equal(report.metrics.unknownRecall, 1);
assert.equal(report.metrics.falseAcceptRate, 0);
assert.equal(report.metrics.falseRejectRate, 0);
assert.equal(report.records.length, 12);
assert(report.records.every(record => Number.isFinite(record.latencyMs)));
assert.throws(() => evaluation.calibrate(modelApi, model, validation.filter(item => item.label !== 'unknown')), /未知协议/);
console.log('model evaluation: 9 assertions across calibration, known accuracy, unknown recall and latency passed');
