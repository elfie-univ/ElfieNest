const surfaceName = object => [
  object?.name || '',
  object?.geometry?.name || '',
  ...(Array.isArray(object?.material) ? object.material.map(material => material?.name || '') : [object?.material?.name || '']),
].join(' ');
const materialCount = object => Array.isArray(object?.material) ? object.material.length : 0;

// The approved courtyard wall is tagged as a sky surface because its material
// uses the authored sky projection. It is still physical boundary geometry and
// must remain visible in the exterior inspection view.
export function isInteriorSkySurface(object) {
  return !!object?.userData?.preview_backdrop
    || !!object?.userData?.preview_dome
    || /roof[_ ]inner[_ ]sky|approved original dome inner sky|sky dome|sky .*dome/i.test(surfaceName(object))
    || (!!object?.userData?.elfienestSkySurface && materialCount(object) >= 5);
}

export function isCourtyardBoundaryWall(object) {
  const name = surfaceName(object);
  return !/dome/i.test(name)
    && /original[_ ]courtyard[_ ]wall[_ ]extended[_ ]vertically|approved[_ -]cube-projected[_ -]original[_ -]boundary|static sky .* wall/i.test(name)
    || (!!object?.userData?.elfienestSkySurface && materialCount(object) === 4);
}

export function overviewRenderLayers(layers, {exterior = false} = {}) {
  if (!exterior) return layers;
  return layers
    .filter(layer => layer.group === 'landscape')
    .map(layer => ({...layer, templateInstances: []}));
}

export function overviewPreviewOptions({exterior = false} = {}) {
  return {
    pixelRatioCap: 1,
    antialias: false,
    powerPreference: 'high-performance',
    transmissionResolutionScale: .5,
    adaptiveGeometry: false,
    motionLod: true,
    shadows: false,
    damping: false,
    // The combined overview keeps furniture available as an explicit toggle,
    // but does not submit every room prop while the courtyard is being orbited.
    showFurnitureByDefault: false,
  };
}
