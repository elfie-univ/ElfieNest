# Estate runtime support

> 中文：[`RUNTIME_zh.md`](RUNTIME_zh.md)

`nest/nest.tscn` loads the sole display assembly, `nest/assembly/estate.tscn`.
Buildings, furniture and courtyard scenes reference their shared GLB prototypes.
The `spatial/` directory holds collision, navigation, semantics and the compiled
snapshot. The `rendering/` directory holds shared lighting, materials and draw
batches. Water, courtyard cover, doors and bedding effects live with their assets.
Godot camera controls and fonts live under `runtime/observer/`.

`assembly/activity_regions.tres` supplies activity permissions. Per-placement
identities and light controls come from `assembly/runtime-bindings.json`.
The compiled physical-only authority retains the same collision geometry,
navigation, contacts and ten operable door leaves without loading display meshes.
Local civil time, lamp switching, water animation and resident effects retain their
existing owners; the split assembly does not introduce another world authority.

After changing formal assets or runtime helpers, run:

```sh
bash scripts/quality/checks/godot_host.sh res://tools/bake_estate_spatial.gd
# Inspect build/estate_spatial/bake-report.json and validate the candidate.
# Publish estate_spatial.res under spatial/ and runtime-inputs.json under assembly/ together.
bash scripts/quality/checks/godot_host.sh res://test/test_estate_precompiled_spatial.gd
./developer.sh build-godot-web
```

Both Web and Linux Dedicated exporters reject a stale source receipt. The Web
physical authority pack is derived from the same full export, retaining physical
and character resources while removing estate display payloads.
`tools/bake_estate_lighting.gd` only snapshots the current regional fixtures into
`build/courtyard-lighting/`; edit their owning split scenes to change lighting.

Use Nest Lab (`./developer.sh nest-lab`, `/nest/experiment`) to inspect assets and
temporary actors. The product `/monitor` observes real residents. Generated
intermediates remain under root `build/`; Godot import caches stay local.
