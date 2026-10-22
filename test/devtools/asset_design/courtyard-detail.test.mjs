import assert from 'node:assert/strict';
import {test} from 'node:test';
import {
  createCourtyardDetail,
  courtyardDetailProfile,
  isCourtyardInstancedVegetation,
} from '../../../devtools/asset_design/web/courtyard-detail.mjs';

test('courtyard detail selects landscape instancing but protects the shell', () => {
  assert.equal(isCourtyardInstancedVegetation({
    isInstancedMesh: true,
    name: 'CY R003 woodland grass and fern layer 0',
    userData: {designObject: 'landscape:site'},
  }), true);
  assert.equal(isCourtyardInstancedVegetation({
    isInstancedMesh: true,
    name: 'Transparent large arch rise25 highest60 above original rim',
    userData: {designObject: 'landscape:site'},
  }), false);
  assert.equal(isCourtyardInstancedVegetation({
    isInstancedMesh: true,
    name: 'pond water surface',
    material: {name: 'Muted blue grey water with moving normals'},
    userData: {designObject: 'landscape:site'},
  }), false);
  assert.equal(isCourtyardInstancedVegetation({
    isInstancedMesh: true,
    name: 'MERGED_SEEDED_shared_leaf_cluster_12',
    material: {name: 'Mixed deep green needles'},
    userData: {designObject: 'landscape:site'},
  }), false);
  assert.equal(isCourtyardInstancedVegetation({
    isInstancedMesh: true,
    name: '',
    userData: {designObject: 'landscape:site'},
  }), true);
  assert.equal(isCourtyardInstancedVegetation({
    isInstancedMesh: false,
    name: 'CY R003 woodland grass and fern layer 0',
    userData: {designObject: 'landscape:site'},
  }), false);
});

test('courtyard detail preserves the source vegetation density in the visual preview', () => {
  const vegetation = {
    isInstancedMesh: true,
    name: 'CY R003 woodland grass and fern layer 0',
    count: 1000,
    geometry: {index: {count: 600}},
    userData: {designObject: 'landscape:site'},
  };
  const shell = {
    isInstancedMesh: true,
    name: 'original courtyard wall',
    count: 1000,
    userData: {designObject: 'landscape:site'},
  };
  const detail = createCourtyardDetail([vegetation, shell]);
  const camera = {position: {toArray: () => [0, 0, 80]}};

  assert.equal(detail.stats().meshes, 1);
  assert.equal(detail.update(camera, {center: [0, 0, 0]}), false);
  assert.equal(vegetation.count, 1000);
  assert.equal(shell.count, 1000);

  camera.position.toArray = () => [0, 0, 5];
  assert.equal(detail.update(camera, {center: [0, 0, 0]}), false);
  assert.equal(vegetation.count, 1000);

  detail.dispose();
  assert.equal(vegetation.count, 1000);
});

test('external courtyard keeps the same full-vegetation visual policy', () => {
  const interior = courtyardDetailProfile();
  const exterior = courtyardDetailProfile({exterior: true});
  assert.equal(interior.preserveVegetation, true);
  assert.equal(exterior.preserveVegetation, true);
  assert.equal(interior.farRatio, 1);
  assert.equal(exterior.farRatio, 1);
  assert.ok(exterior.maxInstances < interior.maxInstances);
});
