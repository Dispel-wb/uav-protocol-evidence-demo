const assert = require('node:assert/strict');
const samples = require('../samples/catalog.json');
const decoder = require('../src/decoder');
const discovery = require('../src/discovery');
const stateAnalysis = require('../src/state-analysis');
const active = require('../src/active-learning');
const fixture = id => decoder.parseHex(samples.find(sample => sample.id === id).hex);

const unknown = fixture('unknown-two-families');
const inferred = discovery.infer(unknown, [{ offset: 0, length: unknown.length }]);
let recommendations = active.recommend({ discovery: inferred, stateAnalysis: { violations: [] } });
assert(recommendations.some(item => item.action.includes('只改变一个')));
assert(recommendations.some(item => item.action.includes('空闲状态')));

const anomalous = decoder.analyze(fixture('mavlink2-anomaly'));
const state = stateAnalysis.analyze(anomalous.frames);
recommendations = active.recommend({ discovery: { families: [], unexplainedBytes: 0 }, stateAnalysis: state });
assert(recommendations.some(item => item.action.includes('完整')));

const diff = active.controlledDiff([
  Uint8Array.of(0xAA, 0x10, 1, 0x55), Uint8Array.of(0xAA, 0x10, 2, 0x55),
], [
  Uint8Array.of(0xAA, 0x20, 3, 0x55), Uint8Array.of(0xAA, 0x20, 4, 0x55),
]);
assert.deepEqual(diff.candidates, [{ offset: 1, before: 0x10, after: 0x20, evidence: '操作前后组内稳定且组间改变' }]);
assert.throws(() => active.controlledDiff([Uint8Array.of(1)], [Uint8Array.of(2)]), /至少需要2帧/);

const candidate = active.propose({ label: 'TEST', bytes: Uint8Array.of(1, 2) }, { experiment: 'controlled-change-1' });
assert.equal(candidate.status, 'candidate');
assert.throws(() => active.appendApprovedExample([], candidate), /未经人工确认/);
const approved = active.approve(candidate, 'reviewer');
const dataset = active.appendApprovedExample([], approved);
assert.equal(dataset.length, 1);
assert.equal(dataset[0].label, 'TEST');
assert.equal(dataset[0].approvedBy, 'reviewer');
console.log('active learning: 10 assertions across recommendations, controlled diffs and approval gating passed');
