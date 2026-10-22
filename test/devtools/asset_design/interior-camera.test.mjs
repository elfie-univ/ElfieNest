import test from 'node:test';
import assert from 'node:assert/strict';

import {
  clampInteriorOrbit,
  courtyardInterior,
  isInteriorPreview,
} from '../../../devtools/asset_design/web/interior-camera.mjs';

test('courtyard previews derive a safe interior orbit from the boundary rim', () => {
  assert.equal(isInteriorPreview('overview'), true);
  assert.equal(isInteriorPreview('landscape:site'), true);
  assert.equal(isInteriorPreview('building:central'), false);

  assert.deepEqual(
    courtyardInterior({min: {x: -50, z: -44}, max: {x: 50, z: 56}}),
    {center: [0, 4.5, 6], radius: 43},
  );
});

test('interior orbit keeps the target centered and clamps the camera inside the rim', () => {
  const interior = courtyardInterior({min: {x: -50, z: -44}, max: {x: 50, z: 56}});
  const orbit = clampInteriorOrbit([0, 4.5, 100], [12, 20, -9], interior);

  assert.deepEqual(orbit.target, [0, 4.5, 6]);
  assert.ok(Math.abs(orbit.position[2] - 49) < 1e-9);
  assert.ok(Math.abs(orbit.position[0]) < 1e-9);
});
