// The courtyard is the camera's safe play area for the combined estate view.
// Keep this math independent of Three.js so the boundary rule stays testable.

export function isInteriorPreview(designObject) {
  return designObject === 'overview' || designObject === 'landscape:site';
}

export function courtyardInterior(bounds, padding = 7, targetY = 4.5) {
  const width = bounds.max.x - bounds.min.x;
  const depth = bounds.max.z - bounds.min.z;
  return {
    center: [
      (bounds.min.x + bounds.max.x) / 2,
      targetY,
      (bounds.min.z + bounds.max.z) / 2,
    ],
    radius: Math.max(2, Math.min(width, depth) / 2 - padding),
  };
}

export function clampInteriorOrbit(position, ignoredTarget, interior) {
  const target = interior.center.slice();
  const offset = position.map((value, index) => value - target[index]);
  const distance = Math.hypot(...offset);
  if (distance <= interior.radius) return {position: position.slice(), target};

  const scale = interior.radius / distance;
  return {
    position: target.map((value, index) => value + offset[index] * scale),
    target,
  };
}
