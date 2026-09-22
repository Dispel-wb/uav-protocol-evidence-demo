const assert = require('node:assert/strict');
const samples = require('../samples/catalog.json');
const decoder = require('../src/decoder');
const discovery = require('../src/discovery');
const intelligence = require('../src/link-intelligence');

function assess(id) {
  const bytes = decoder.parseHex(samples.find(sample => sample.id === id).hex);
  const parsed = decoder.analyze(bytes);
  const inferred = discovery.infer(bytes, parsed.gaps);
  return intelligence.assess(bytes, parsed, inferred);
}

let result = assess('mavlink2-normal');
assert.equal(result.classification, '已知协议链路');
assert.equal(result.confidence, '高');
assert.equal(result.metrics.coveragePercent, 100);
assert.equal(result.metrics.integrityPercent, 100);
assert.equal(result.metrics.protocolCount, 1);
assert.deepEqual(result.sessions.mavEndpoints, ['1/1', '255/190']);

result = assess('mixed-capture');
assert.equal(result.metrics.protocolCount, 2);
assert.equal(result.metrics.transitions, 2);
assert.equal(result.metrics.coveragePercent, 100);

result = assess('unknown-two-families');
assert.equal(result.classification, '未知结构候选链路');
assert.equal(result.metrics.inferredBytes, result.metrics.totalBytes);
assert.equal(result.sessions.unknownFamilies, 2);
assert.equal(result.confidence, '高');

result = assess('mavlink-crc-error');
assert.equal(result.metrics.integrityPercent, 0);
assert(result.nextActions.some(action => action.includes('CRC')));

const noise = Uint8Array.from({length: 96}, (_, index) => (index * 73 + 19) & 255);
const parsed = decoder.analyze(noise);
const inferred = discovery.infer(noise, parsed.gaps);
result = intelligence.assess(noise, parsed, inferred);
assert.equal(result.classification, '证据不足');
assert.equal(result.metrics.coveragePercent, 0);
assert.equal(result.confidence, '低');
console.log('link intelligence: 18 assertions across known, mixed, unknown, corrupt and noise captures passed');
