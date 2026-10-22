import assert from 'node:assert/strict';
import {test} from 'node:test';
import {
  isCourtyardBoundaryWall,
  isInteriorSkySurface,
  overviewRenderLayers,
  overviewPreviewOptions,
} from '../../../devtools/asset_design/web/preview-policy.mjs';

test('courtyard boundary wall is not mistaken for the interior sky surface', () => {
  const wall = {
    name: 'Original_courtyard_wall_extended_vertically_R50_centerZ6',
    geometry: {name: 'Approved_cube-projected_original_boundary'},
    material: {name: 'Approved static sky px wall'},
    userData: {elfienestSkySurface: true},
  };
  const roof = {
    name: 'ROOF_INNER_SKY_FINAL',
    userData: {elfienestSkySurface: true},
  };

  assert.equal(isCourtyardBoundaryWall(wall), true);
  assert.equal(isInteriorSkySurface(wall), false);
  assert.equal(isInteriorSkySurface(roof), true);
  assert.equal(isCourtyardBoundaryWall({
    material: [{}, {}, {}, {}],
    userData: {elfienestSkySurface: true},
  }), true);
  assert.equal(isInteriorSkySurface({
    material: [{}, {}, {}, {}, {}],
    userData: {elfienestSkySurface: true},
  }), true);
  const domeChild = {
    name: 'Approved_cube-projected_original_boundary_4',
    material: {name: 'Approved static sky py dome'},
    userData: {elfienestSkySurface: true},
  };
  assert.equal(isInteriorSkySurface(domeChild), true);
  assert.equal(isCourtyardBoundaryWall(domeChild), false);
});

test('overview exterior preview uses the responsive inspection profile', () => {
  assert.deepEqual(overviewPreviewOptions({exterior: true}), {
    pixelRatioCap: 1,
    antialias: false,
    powerPreference: 'high-performance',
    transmissionResolutionScale: .5,
    adaptiveGeometry: false,
    motionLod: true,
    shadows: false,
    damping: false,
    showFurnitureByDefault: false,
  });
  assert.equal(overviewPreviewOptions().showFurnitureByDefault, false);
});

test('overview exterior preview loads only the approved courtyard shell', () => {
  const layers = [
    {group: 'building', templateInstances: [{file: 'furniture.glb'}]},
    {group: 'landscape', templateInstances: [{file: 'ignored.glb'}]},
  ];
  assert.deepEqual(overviewRenderLayers(layers, {exterior: true}), [
    {group: 'landscape', templateInstances: []},
  ]);
  assert.strictEqual(overviewRenderLayers(layers), layers);
});
