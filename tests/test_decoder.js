const assert=require('node:assert/strict');
const samples=require('../samples/catalog.json');
const lab=require('../src/decoder.js');
const fixture=id=>lab.parseHex(samples.find(x=>x.id===id).hex);
function titles(result){return result.findings.map(x=>x.title)}

let r=lab.analyze(fixture('mavlink2-normal'));
assert.equal(r.summary.frames,7);assert.equal(r.summary.findings,0);
assert(r.frames.every(x=>x.crc==='valid'));
assert.equal(r.frames[4].fields.armed,true);
assert.equal(r.frames[5].fields.command,22);
assert.equal(r.frames[5].fields.param7,50);

r=lab.analyze(fixture('mavlink2-anomaly'));
assert.equal(r.summary.frames,3);
assert.deepEqual(titles(r),['起飞前未确认解锁','起飞高度超出配置范围','GPS 定位不足']);
r=lab.analyze(fixture('mavlink1-telemetry'));
assert.equal(r.summary.frames,2);assert.equal(r.summary.findings,0);
assert.equal(r.frames[0].family,'MAVLink 1');
assert(Math.abs(r.frames[1].fields.yawDeg-68.7549)<0.01);

r=lab.analyze(fixture('sbus-healthy'));
assert.equal(r.summary.frames,2);assert.equal(r.summary.findings,0);
assert.deepEqual(r.frames[0].channels,[1024,1024,1024,1024,1024,1024,1024,1024,1024,1024,1024,1024,1024,1024,1024,1024]);
assert.deepEqual(r.frames[1].channels.slice(0,4),[1100,900,1000,1200]);
assert(titles(lab.analyze(fixture('sbus-failsafe'))).includes('SBUS failsafe'));
assert(titles(lab.analyze(fixture('sbus-lost'))).includes('连续丢帧'));
assert.equal(lab.analyze(fixture('sbus-lost'),{sbusLostFrameLimit:3}).summary.findings,0);
assert(titles(lab.analyze(fixture('mavlink-crc-error'))).includes('CRC 校验失败'));
r=lab.analyze(fixture('mixed-capture'));
assert.equal(r.summary.mavlink,2);assert.equal(r.summary.sbus,1);

r=lab.analyze(fixture('mavlink2-normal'),{maxAltitudeM:30});
assert(titles(r).includes('起飞高度超出配置范围'));
r=lab.analyze(fixture('mavlink2-anomaly'),{requireArmAck:false,minGpsFix:2,maxAltitudeM:200});
assert.equal(r.summary.findings,0);

assert.throws(()=>lab.parseHex('0xFE 0xZ2'),/非/);
assert.throws(()=>lab.parseHex('FED'),/偶数/);
assert.equal(lab.scan(fixture('mavlink2-normal').slice(0,4)).gaps[0].incomplete,true);
const unknown=fixture('mavlink2-normal').slice(0,21);unknown[7]=200;
assert.equal(lab.analyze(unknown).frames[0].crc,'unknown-definition');
assert.equal(lab.analyze(Uint8Array.from([0xaa,0xbb,...fixture('sbus-failsafe')])).gaps[0].length,2);
console.log('decoder: 22 assertions across 8 captures and rule variants passed');
