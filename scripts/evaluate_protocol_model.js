const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const samples = require(path.join(root, 'samples/catalog.json'));
const manifest = require(path.join(root, 'samples/model-dataset.json'));
const decoder = require(path.join(root, 'src/decoder'));
const discovery = require(path.join(root, 'src/discovery'));
const modelApi = require(path.join(root, 'src/protocol-model'));
const evaluation = require(path.join(root, 'src/model-evaluation'));
const fixture = id => decoder.parseHex(samples.find(sample => sample.id === id).hex);

function knownFrames(record) {
  return decoder.scan(fixture(record.capture)).frames.map((frame, index) => ({ id: `${record.capture}-${index}`, label: record.label, group: record.group, bytes: decoder.parseHex(frame.raw) }));
}
function expand(record) {
  if (record.label !== 'unknown') return knownFrames(record);
  const bytes = fixture(record.capture), inferred = discovery.infer(bytes, [{ offset: 0, length: bytes.length }]);
  return inferred.families.flatMap((family, familyIndex) => family.packets.map((packet, index) => ({ id: `${record.capture}-${familyIndex}-${index}`, label: 'unknown', group: `${record.group}-${familyIndex}`, bytes: bytes.slice(packet.offset, packet.offset + packet.length) })));
}

const training = manifest.records.filter(record => record.partition === 'train').flatMap(expand);
const validation = manifest.records.filter(record => record.partition === 'validation').flatMap(expand);
const model = modelApi.train(training);
const calibration = evaluation.calibrate(modelApi, model, validation);
const result = evaluation.evaluate(modelApi, model, validation, calibration);
const report = { schema: 'protocol-model-experiment-v1', generatedAt: new Date().toISOString(), manifest: 'samples/model-dataset.json', trainingExamples: training.length, validationExamples: validation.length, groups: [...new Set(validation.map(item => item.group))], calibration, evaluation: result.metrics, records: result.records, limitations: manifest.limitations };
const output = path.join(root, 'reports/protocol_model_evaluation.json');
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log(output);
console.log(JSON.stringify(result.metrics));
