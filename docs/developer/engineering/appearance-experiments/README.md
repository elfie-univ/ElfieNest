# Appearance Experiments

This directory is the durable record for dog/fox appearance variation experiments.

## Current decision map

- [Phase 1 — material recoloring](phase-1-material-recoloring.md): accepted visual baseline for
  coat color, light/dark regions, fur shading, and fur texture.
- [Phase 2 — patterns, marks, and candidate diversity](phase-2-patterns-and-marks.md): completed
  feasibility plates for large natural regions, color-slot permutations, local marks, safe zones,
  and five-candidate variation.
- [Phase 3 — production semantic regions](phase-3-region-discovery.md): the frozen thirteen-region
  runtime contract and its compact four-view dog/fox baseline.
- UV-mask prototype: explicitly rejected as the current production solution after front/side
  visual review; retained only as historical evidence in the task closure record.

## Frozen boundaries

The experiments do not modify GLB geometry, BlendShapes, face shape, or the adoption service. Old
image-space and discovery harnesses were removed after their decisions were promoted, so runtime
recoloring and region classification have one source in `ActorAppearance`.
