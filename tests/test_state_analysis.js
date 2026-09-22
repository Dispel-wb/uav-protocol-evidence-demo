const assert = require('node:assert/strict');
const samples = require('../samples/catalog.json');
const decoder = require('../src/decoder');
const stateAnalysis = require('../src/state-analysis');
const fixture = id => decoder.parseHex(samples.find(sample => sample.id === id).hex);

let parsed = decoder.analyze(fixture('mavlink2-normal'));
let state = stateAnalysis.analyze(parsed.frames);
assert.equal(state.finalState, 'takeoff-accepted');
assert.deepEqual(state.links.map(link => link.command), ['ARM_DISARM', 'TAKEOFF']);
assert.equal(state.links[0].requestOffset, 63);
assert.equal(state.links[0].ackOffset, 107);
assert.equal(state.violations.length, 0);
assert(state.timeline.some(item => item.to === 'armed'));
assert(state.timeline.some(item => item.to === 'takeoff-requested'));

parsed = decoder.analyze(fixture('mavlink2-anomaly'));
state = stateAnalysis.analyze(parsed.frames);
assert.equal(state.finalState, 'takeoff-requested');
assert(state.violations.some(item => item.type === 'precondition'));
assert(state.violations.some(item => item.type === 'missing-ack'));

const ackOnly = decoder.analyze(fixture('mavlink2-normal').slice(107, 129));
state = stateAnalysis.analyze(ackOnly.frames);
assert(state.violations.some(item => item.type === 'orphan-ack'));
assert.equal(state.links.length, 0);
console.log('state analysis: 13 assertions across normal, missing-precondition and orphan-ack sessions passed');
