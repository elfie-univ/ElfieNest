const PROTECTED_SURFACES = /water|pond|fountain|wall|dome|roof|arch|path|stone|clay/i;
const PROTECTED_TREE_CANOPIES = /leaf[_ ]?cluster|deep green needles|canopy|tree crown|tree foliage/i;

function surfaceName(object) {
  return [
    object?.name || '',
    object?.geometry?.name || '',
    ...(Array.isArray(object?.material)
      ? object.material.map(material => material?.name || '')
      : [object?.material?.name || '']),
  ].join(' ');
}

// The source courtyard keeps the wall, dome, water and paths as ordinary
// geometry. Only the very large GPU-instanced living layers are eligible for
// this disposable runtime preview policy.
export function isCourtyardInstancedVegetation(object) {
  if (!object?.isInstancedMesh || object.userData?.designObject !== 'landscape:site') return false;
  const name = surfaceName(object);
  // Tree crowns are a primary silhouette of the approved courtyard. Keep
  // them at full instance density; only low groundcover, flowers and shrubs
  // may enter the disposable detail budget.
  if (PROTECTED_TREE_CANOPIES.test(name)) return false;
  // The approved courtyard shell is ordinary geometry. Treat every other
  // landscape instanced draw as disposable detail, including unnamed source
  // nodes whose exporter dropped their vegetation label.
  return !PROTECTED_SURFACES.test(name);
}

export function courtyardDetailProfile({exterior = false} = {}) {
  return exterior
    ? {preserveVegetation: true, nearDistance: 24, farDistance: 92, farRatio: 1, maxInstances: 1200, maxTriangles: 100000, minInstances: 24}
    : {preserveVegetation: true, nearDistance: 9, farDistance: 52, farRatio: 1, maxInstances: 1800, maxTriangles: 160000, minInstances: 32};
}

function smoothStep(value) {
  return value * value * (3 - 2 * value);
}

function instanceRatio(distance, profile) {
  if (!Number.isFinite(distance) || distance <= profile.nearDistance) return 1;
  if (distance >= profile.farDistance) return profile.farRatio;
  const progress = (distance - profile.nearDistance) / (profile.farDistance - profile.nearDistance);
  return 1 - (1 - profile.farRatio) * smoothStep(progress);
}

function distanceToCenter(position, center) {
  const values = typeof position?.toArray === 'function' ? position.toArray() : position;
  if (!Array.isArray(values) || values.length < 3 || !values.every(Number.isFinite)) return Infinity;
  return Math.hypot(values[0] - center[0], values[1] - center[1], values[2] - center[2]);
}

export function createCourtyardDetail(meshes, {exterior = false} = {}) {
  const profile = courtyardDetailProfile({exterior});
  const records = meshes
    .filter(isCourtyardInstancedVegetation)
    .filter(mesh => Number.isFinite(mesh.count) && mesh.count > 0)
    .map(mesh => ({mesh, originalCount: mesh.count}));
  let closed = false;
  let lastDistance = null;
  let lastCenter = null;

  function update(camera, {center = [0, 0, 0], force = false} = {}) {
    if (closed) return false;
    if (profile.preserveVegetation) return false;
    const distance = distanceToCenter(camera?.position, center);
    if (!force && lastDistance !== null && Math.abs(distance - lastDistance) < 1 &&
        lastCenter?.every((value, index) => value === center[index])) return false;
    lastDistance = distance;
    lastCenter = center.slice();
    const ratio = instanceRatio(distance, profile);
    let changed = false;
    for (const record of records) {
      const {mesh, originalCount} = record;
      const minimum = Math.min(originalCount, profile.minInstances);
      const triangles = mesh.geometry?.index?.count
        ? mesh.geometry.index.count / 3
        : (mesh.geometry?.attributes?.position?.count || 0) / 3;
      const triangleCap = triangles > 0 ? Math.floor(profile.maxTriangles / triangles) : profile.maxInstances;
      const cap = ratio >= 1
        ? originalCount
        : Math.max(minimum, Math.min(profile.maxInstances, triangleCap));
      const target = Math.max(minimum, Math.min(cap, Math.floor(originalCount * ratio)));
      if (mesh.count !== target) {
        mesh.count = target;
        changed = true;
      }
    }
    return changed;
  }

  function stats() {
    const originalInstances = records.reduce((sum, record) => sum + record.originalCount, 0);
    const activeInstances = records.reduce((sum, record) => sum + record.mesh.count, 0);
    return {
      meshes: records.length,
      originalInstances,
      activeInstances,
      reductionRatio: originalInstances ? 1 - activeInstances / originalInstances : 0,
      profile,
    };
  }

  function dispose() {
    if (closed) return;
    for (const {mesh, originalCount} of records) mesh.count = originalCount;
    records.length = 0;
    closed = true;
  }

  return {update, stats, dispose};
}
