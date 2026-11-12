# Forest foliage intermediate LOD

This import-only tool appends the reviewed **2000-triangle** level to
`forest-foliage.glb` / `part_00006`. The original 2304-triangle base, its native
vertex/normal/tangent/color bytes, material, and the existing 840/240-triangle
LODs remain intact. The position-welded shadow mesh receives the corresponding
index-only level; its base and existing levels remain intact too. There is no UV
attribute on this prototype. Runtime code does not read the sidecar.

The sidecar is reproducible derived import data, not another geometry source.
Source GLB, placement inputs used for the scale bound, native buffers, complete
non-material surface fields, and old LODs are checked before binding. A mismatch
fails import rather than attaching stale indices. Materials are retained by
Resource identity. No vertex attributes are re-encoded. Changing a placement
requires regeneration even if its geometry is unchanged, because its fingerprint
is part of the current effective-scale proof.

## Regenerate

From the repository root, with the existing locked Developer Tools dependencies
and `zstd` available (the tool installs nothing):

```sh
.venv/bin/python3 godot_project/tools/foliage_lod/read_baseline.py
node godot_project/tools/foliage_lod/generate.mjs
node godot_project/tools/foliage_lod/map_native.mjs build/godot_assets/foliage-lod-regenerated --write-sidecar
```

The Python command reads the existing Godot 4.7 import cache identified by the
asset's `.import` file and current formal SCN instance buffers. It never runs
Godot or writes its cache. It accepts either the original cache or a cache with
exactly the previously generated extra LOD, stripping only that known pair for
comparison. An absent cache requires an owner-controlled baseline import first.
No engine binary or cache filename is hardcoded. A changed GLB needs a new
quality review; the generator deliberately rejects a different source hash.

All diagnostic outputs go to `build/godot_assets/foliage-lod-regenerated/`.
Only the final command's explicit `--write-sidecar` updates the adjacent
`forest-foliage.lods.json`; omit that flag for a build-only regeneration.
The existing Three.js bundled meshoptimizer generates indices only, with
attribute seams, component extrema and borders locked. Only 2000 is generated;
1800 and 1600 remain excluded. Their earlier nearest-point normal/orientation
correspondence checks failed; those results do not prove actual flipped faces.

## Verification and integration

The geometric verifier bounds both directions by mapping each subdivided
triangle patch to a single target triangle via convex correspondence, with a
1e-7 m numerical allowance. The reviewed prototype bound is
0.006613091778341079 m; the current placement stretch bound is
1.0882338673315108, giving 0.007196590440962331 m in world space.
The stored LOD edge is rounded **up** to float32: 0.007196597754955292.
Interpolation checks are sampled (normal maximum 1.631 degrees, tangent 3.740
degrees, color channel 0.003992); these are not a claim of pixel equivalence.

The native mapper checks a bijection using exact positions/colors, tangent sign,
and tolerances limited to existing oct16 normal/tangent decoding. It verifies
the full oriented base triangle multiset, including the importer's winding
reversal, and maps the shadow indices separately by exact position.

Owner-controlled sequence, through the repository Godot toolchain boundary:

1. Explicitly reimport `res://nest/courtyard/parts/forest/forest-foliage.glb`.
   Sidecar changes alone are not guaranteed to trigger Godot's import watcher.
2. Run the focused SceneTree script with engine arguments
   `--headless --path godot_project --script res://test/test_foliage_lod_import.gd`.
   It requires the imported candidate, checks its exact index bytes and all
   baseline surface/LOD fingerprints, compares a reapplication to the baseline,
   and rejects stale source/placement/buffer and invalid index/error inputs.
3. Rebake/export and validate the real Web near view, LOD transition and shadows.

The author did not run Godot. Native import/test and visual acceptance remain
for the serial owner. Candidate selection saves 304 triangles per selected
instance (13.19% of this prototype), not draw calls; FPS improvement is unmeasured.
Rollback is to clear this asset's `import_script/path` and reimport the same
unchanged GLB; no base geometry or old LOD is overwritten.
