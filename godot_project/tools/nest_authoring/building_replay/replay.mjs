import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Reproduce the earlier optimization from its saved inputs, without installing
// any assets or relying on the original build directory.
const tools = path.dirname(fileURLToPath(import.meta.url));
const root = fileURLToPath(new URL('../../../../', import.meta.url));
const archive = path.join(tools, '../.archive');
const scratch = path.join(root, 'build/godot_assets/nest-authoring');
const mode = process.argv[2] ?? 'geometry';
assert(['geometry', 'storage'].includes(mode), 'Use geometry or storage');
const history = mode === 'geometry' ? 'building-geometry' : 'building-byte-storage';
const inventory = JSON.parse(fs.readFileSync(path.join(archive, 'inventory.json'), 'utf8'));
const digest = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function archived(name) {
  const key = `godot_assets/${history}/${name}`;
  const item = inventory.files[key];
  assert(item && /^[a-f0-9]{64}$/.test(item.sha256), `Missing archive input: ${key}`);
  const blob = path.join(archive, 'objects', item.sha256);
  assert.equal(digest(blob), item.sha256, `Archive input changed: ${key}`);
  return blob;
}
const load = name => JSON.parse(fs.readFileSync(archived(name), 'utf8'));
const report = mode === 'geometry' ? load('summary.json') : load('report.json');
const models = {
  main: 'main/central-building.glb',
  pod: 'pod/pod-building.glb',
};
const expect = mode === 'geometry'
  ? report.map(row => [models[row.type], row.before.sha256, row.after.sha256])
  : report.map(row => [row.file, row.beforeSha256, row.afterSha256]);
assert.deepEqual(expect.map(row => row[0]).sort(), Object.values(models).sort());
const buildings = path.join(root, 'godot_project/nest/buildings');
fs.mkdirSync(scratch, { recursive: true });
const work = fs.mkdtempSync(path.join(scratch, 'replay-'));
for (const stage of ['before', 'candidates']) {
  fs.mkdirSync(path.join(work, stage));
  fs.symlinkSync(path.join(buildings, 'textures'), path.join(work, stage, 'textures'));
}
for (const [file, expected] of expect) {
  const from = archived(`before/${file}`);
  const to = path.join(work, 'before', file);
  assert.equal(digest(from), expected, file);
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
  fs.mkdirSync(path.dirname(path.join(work, 'candidates', file)), { recursive: true });
}

function run(script) {
  const command = spawnSync(
    process.execPath, [path.join(tools, script), work], { stdio: 'inherit' },
  );
  if (command.error) throw command.error;
  assert.equal(command.status, 0, `${script} failed`);
}

if (mode === 'geometry') {
  for (const file of ['scene-baseline.json', 'attribute-comparison.json']) {
    fs.copyFileSync(archived(file), path.join(work, file));
  }
  run('process.mjs');
  run('finalize.mjs');
} else {
  run('byte-storage.mjs');
}
for (const [file, , expected] of expect) {
  const result = path.join(work, mode === 'geometry' ? 'verified' : 'candidates', file);
  assert.equal(digest(result), expected, `Replayed bytes differ: ${file}`);
  if (mode === 'geometry') {
    assert.equal(expected, digest(path.join(buildings, file)), `Runtime asset differs: ${file}`);
  }
  console.log(`Verified ${file}: ${expected}`);
}
console.log(`Replay artifacts: ${work}`);
