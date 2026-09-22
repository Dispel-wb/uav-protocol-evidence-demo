const assert = require('node:assert/strict');
const samples = require('../samples/catalog.json');
const decoder = require('../src/decoder');
const discovery = require('../src/discovery');
const modelApi = require('../src/protocol-model');
const fixture = id => decoder.parseHex(samples.find(sample => sample.id === id).hex);

function frames(id) { return decoder.scan(fixture(id)).frames.map(frame => decoder.parseHex(frame.raw)); }
const training = [
  ...frames('mavlink2-normal').map(bytes => ({ label: 'MAVLink', bytes })),
  ...frames('sbus-healthy').map(bytes => ({ label: 'SBUS', bytes })),
];
const model = modelApi.train(training);
assert.deepEqual(model.labels, ['MAVLink', 'SBUS']);
assert.equal(model.counts.MAVLink, 7);
assert.equal(model.counts.SBUS, 2);

for (const bytes of frames('mavlink2-anomaly')) assert.equal(modelApi.predict(model, bytes).label, 'MAVLink');
assert.equal(modelApi.predict(model, frames('sbus-failsafe')[0]).label, 'SBUS');

const unknownBytes = fixture('unknown-two-families');
const inferred = discovery.infer(unknownBytes, [{ offset: 0, length: unknownBytes.length }]);
for (const family of inferred.families) {
  for (const packet of family.packets) {
    const result = modelApi.predict(model, unknownBytes.slice(packet.offset, packet.offset + packet.length));
    assert.equal(result.label, 'unknown');
    assert.equal(result.accepted, false);
  }
}
assert.throws(() => modelApi.train([{ label: 'only', bytes: Uint8Array.of(1) }, { label: 'only', bytes: Uint8Array.of(2) }]), /两个协议类别/);
console.log('protocol model: 23 assertions across held-out known frames and two rejected unknown families passed');
