# Estate source and functional replays

> 中文：[`README_zh.md`](README_zh.md)

`res://nest/estate/estate.tscn` loads one complete estate through `nest/nest.tscn`.
Buildings, furniture, base meshes and materials retain the committed baseline.
The integrated GLB adds the approved forest loop, return spur, smooth ground regions,
path-side vegetation changes and nine retained outdoor fixtures (E01–E02, R01–R07).
The scene's `source_sha256` records the original desktop export; `integrated_model_sha256`
and `instance_sidecar_sha256` identify the current integrated inputs.

| Source resource | Current contents |
| --- | --- |
| `ElfieNest-complete-final.glb` | 266,635,048 bytes; selected terrain/fixture additions over the baseline |
| `ElfieNest-complete-final.instances.bin` | 134 landscape groups, 214,448 instances; 13,728,712 bytes |
| `estate_outdoor_lighting.scn` | Authored road/plaza guidance, lake-bank rim, four high poles (including the inward-facing 6.5 m single-arm streetlight pair with solid opal diffusers and broad overlapping beams aimed at the centre to cover the full plaza, and one matching full-size 6.5 m single-arm waterfront lamp), two full-size 1.17 m ring-road-style approach lamps, and 23 forest lamps |
| `estate_spatial.res` | Current-model collision shapes, activity boundaries and native navigation/stair links |

Runtime loads precompiled spatial data and rejects mismatched model, instance or lighting
inputs. Roads, plaza, lawn and the forest path connect; planting, water, facilities and
simplified trunks remain protected. The movement boundary is excluded from perception rays.
Ten physical door leaves (eight authored and two garden) share proximity opening, delayed
closure, reversal and occupied-volume protection. An explicit default-open setter is available;
connecting that policy to the world's day/night phase remains separate from this migration.

Nest supplies local civil time: 06–18 day, 18–24 evening, 00–06 quiet hours. Ordinary lamps and
authored emission follow the same switch; quiet hours retain guidance and occupied-room policy.
Surfaces receive actual lights without the rejected fixed warm term. The product monitor has
independent time/view selectors; preview changes do not alter Nest or residents.

The regular camera catalog contains one courtyard view, four central floors and eight
bedroom/terrace pairs. The monitor adds forest/estate access views and a ring-road view.
Orbit, zoom, limited pan, current-view reset and actor-follow offsets remain available.

Use the product `/monitor` page to inspect the complete estate and real residents.
The separate Developer Tools `/nest/experiment` page remains available for isolated
Nest Lab experiments. Its temporary actors and simulation controls do not operate on
production residents. The asset workbench remains at `/assets/design`.

Standalone animation journeys and camera, chair, water, collision and lighting review
pages have been retired. Their query parameters no longer select a review mode.
Monitor retains its existing debug-only time preview and normal camera controls.

Production arrival timing, petal/column/dome lighting and the hosted-body cover live
in `nest/estate/estate_platform_cycle.gd`, `estate_arrival_lighting.gd`,
`estate_petal_charge.gd`, `estate_event_effects.gd` and their adjacent shaders.
`runtime/actor/adoption_arrival.gd` owns the physical arrival trajectory;
`runtime/observer/resident_effects.gd` binds effects to real resident state.
Adoption only arrives; hosting leaves the physical body in its bed. No departure
teleport or audio is introduced. Skeletal source clips remain in `characters/animation/`.
The product scene and effects do not import `runtime/lab`; the Lab bridge is loaded
only when an explicit Elfie Lab or Nest Lab mode is requested.

Offline authoring uses the repository's controlled Godot host entry:

```sh
bash scripts/quality/checks/godot_host.sh res://tools/bake_estate_lighting.gd
# Inspect build/estate-lighting-v4/estate_outdoor_lighting.scn, then publish it here.
bash scripts/quality/checks/godot_host.sh res://tools/bake_estate_spatial.gd
# Inspect build/estate_spatial/bake-report.json, then publish estate_spatial.res here.
bash scripts/quality/checks/godot_host.sh res://test/test_estate_precompiled_spatial.gd
```

Intermediates stay under `build/`; final authored resources above are source assets.
Godot import caches remain local and excluded from Git. Web output is produced only by
`./developer.sh build-godot-web` into `build/components/godot-web/`.
