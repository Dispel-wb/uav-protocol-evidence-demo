const assert = require('node:assert/strict');
const samples = require('../samples/catalog.json');
const decoder = require('../src/decoder');
const discovery = require('../src/discovery');
const intelligence = require('../src/link-intelligence');
const streaming = require('../src/stream-intelligence');

const fixture = id => decoder.parseHex(samples.find(sample => sample.id === id).hex);
const dependencies = { decoder, discovery, intelligence };

let session = streaming.create(dependencies, { windowBytes: 128 });
const heartbeat = fixture('mavlink2-normal').slice(0, 21);
let report = session.push({ timestampMs: 1000, bytes: heartbeat.slice(0, 9), source: 'test' });
assert.equal(report.parsed.frames.length, 0);
assert.equal(report.parsed.gaps[0].incomplete, true);
report = session.push({ timestampMs: 1100, bytes: heartbeat.slice(9), source: 'test' });
assert.equal(report.parsed.frames.length, 1);
assert.deepEqual(report.changes.appeared, ['MAVLink 2']);
assert.equal(report.stream.instantaneousBytesPerSecond, 120);
assert.equal(report.stream.totalBytes, 21);

session = streaming.create(dependencies, { windowBytes: 25 });
report = session.push({ timestampMs: 0, bytes: heartbeat });
assert.deepEqual(report.changes.appeared, ['MAVLink 2']);
report = session.push({ timestampMs: 50, bytes: fixture('sbus-failsafe'), dropped: true });
assert.deepEqual(report.changes.appeared, ['SBUS']);
assert.deepEqual(report.changes.disappeared, ['MAVLink 2']);
assert.equal(report.stream.retainedBytes, 25);
assert.equal(report.stream.droppedChunks, 1);
assert.equal(report.linkAssessment.metrics.protocolCount, 1);

assert.throws(() => session.push({ timestampMs: 40, bytes: Uint8Array.of(1) }), /单调/);
session.reset();
assert.throws(() => session.push({ timestampMs: 1, bytes: [] }), /不能为空/);
console.log('stream intelligence: 16 assertions across split frames, sliding windows, transitions and drop metadata passed');
