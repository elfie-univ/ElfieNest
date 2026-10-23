# Estate complete final asset

> 中文：[`README_zh.md`](README_zh.md)

Open `res://rooms/estate/estate.tscn` in the repository's Godot 4.7 project.
The scene now contains one self-contained final GLB with the complete building,
real interiors, terraces and approved courtyard. Legacy procedural rooms,
standalone furniture and the central/pod baseline have been removed from source
and export inputs. A local recoverable copy is outside the project under
`build/asset_exports/retired-rooms-20261022/`.

| Resource | Contents | Size |
| --- | --- | --- |
| `ElfieNest-complete-final.glb` | Godot-compatible complete building, interiors, terraces and courtyard export | 251,670,216 bytes |
| `ElfieNest-complete-final.instances.bin` | Lossless world-space transforms for the final GLB's repeated-instance groups | 13,875,592 bytes |

`main.tscn` uses the original `rooms/nest.tscn` / `ModularNest` owner, which retains
camera and Observer behavior and loads this complete asset once instead of generating
the old corridor rooms. The 15 views include the courtyard, sky, central floors
and eight furnished dorms. Run the standard Web build, then open
`elfienest.html?mode=nest_lab` for the in-engine view selector and orbit controls.
The default dorm view looks across the near bed/chair pair so the first
interaction seat is in frame, rather than behind the camera.

Daylight uses the workbench's authored reflection gradient, ACES response and
asset-local fixture definitions at 8% output, with furniture-only contact shadows.
Painted and needle crown instances retain their exact base vertex/index buffers
without the importer's silhouette-reducing LOD alternatives. Source colors,
roughness, textures and instance transforms are unchanged. The courtyard camera
matches the central V050 front reference (42-degree FOV, two 0.8 zoom steps).

Landscape transforms are partitioned into 16 m horizontal cells and batches of
at most 128 instances, sharing the original meshes/materials. This bounds draw
submissions and enables spatial culling without removing geometry. Room fixtures
do not illuminate landscape batches. The Web entry requests a high-performance
GPU; the browser decides which device is available, and discrete GPU use can
increase power consumption. This request does not reduce rendering quality.
The source-only post-import hook carries authored clearcoat/IOR/transmission
values into material metadata, so Web uses the same values without reading a raw
GLB at runtime. The importer itself is excluded from exported Runtime bundles.

`ModularNest` binds runtime collisions and semantic anchors from this asset's
module/floor/furniture metadata: 32 beds, 32 desk chairs, two garden seats, eight
sliding doors, four central levels, eight terraces and the courtyard. Bed capacity
only activates the corresponding bed/chair catalogue; it never rebuilds the rooms.
The six authored garden collision proxies are reused and foliage is not baked.
Mirrored geometry keeps a positive-handed physics frame. Rendering visibility,
including hidden authority mode, never disables collisions.

Navigation readiness checks every advertised approach and route to the courtyard
after all regions synchronize. The real half-landing tops provide inset turning
navigation patches and links to their actual stair treads; Actors still walk with
full capsules, gravity and swept step clearance. `furniture.use` navigates to a
source-bound approach before entering its bed/seat pose. Occupancy, cancellation
and blocked exits are explicit outcomes. Water flow and cloud movement remain
static export data. The camera-only Nest Lab is not an autonomous-life acceptance.

Collision resources share exact triangle bytes across render-material variants.
Triangles are read from indexed surfaces without generating a picking BVH for
every render mesh; convex furniture uses its actual hull. The visible GLB is
unchanged, with no triangle decimation or texture reduction. The full physical
world with real actors measured approximately 1.61 GiB stage RSS, not peak or
browser/GPU memory. The acceptance scenario covers courtyard return, bed/chair
use, cancellation/occupancy and maximum-size actors on real central/terrace stairs.

`test_complete_estate_world.gd` validates physical actions, while
`test_observer_real_actions.gd` checks strict semantic replay and mid-walk pause.
`scripts/internal/diagnostics/verify_nest_runtime_e2e.py` connects real Gateway,
NativeBody and Nest pose projections to `main.tscn`; its resident identities are
fixtures, not Brain/Provider or autonomous-life acceptance.

The GLB embeds its image data and has no external texture files. Godot 4.7 does
not support the source file's `EXT_mesh_gpu_instancing`, so the repository copy
removes that unsupported wrapper and restores its 134 groups / 216,743 instances
through `MultiMeshInstance3D` using the sidecar. Identical images (224 → 91),
textures (310 → 183), materials (1,123 → 471) and meshes (2,140 → 2,016) now share
references. All 8,507 node identities, metadata and transforms are preserved;
the two superseded white entrance-step nodes no longer reference render meshes,
while binary data and instance transforms remain byte-identical. This is
resource sharing plus the approved entrance-step removal, not texture resizing
or mesh simplification. The current desktop export is 251,879,364 bytes with
SHA-256 `30c4f8e7889b03b7da61a68b23f7a640c901267ba0de8c314b4678cc819e8e32`.

The Godot copy SHA-256 is `5538b1f675cbc532c920eb7543e1b1fd7f16f2c097ab5180297b425148b8f973`.
The sharing pass is reproducible with `scripts/internal/build/optimize_estate_glb.py`;
it writes a separate output and never modifies the desktop source.

Sidecar v1 stores `name_length, instance_count, name, matrices` per group. Reading
the count after the name interpreted the first group as 808,464,479 instances
instead of 2,418 and attempted a 36 GiB allocation. The reader now matches the
writer, validates lengths before allocating, uploads transforms in bulk, and
preserves per-surface materials and vertex colors. No geometry or textures were
reduced. Before physics integration, the focused headless check measured asset RSS falling from
1,194.8 MiB to 951.4 MiB (20.4%) and main-scene RSS from 1,351.8 MiB to
1,101.1 MiB (18.5%). This excludes browser/GPU memory and is not a peak-memory
guarantee. The validation process took 4.05 s including class/resource preloads;
the one-time import took 75.6 s. Script-local elapsed times exclude preloads.
The focused test also checks all group counts, first/last transform samples,
vertex colors and the main scene's camera catalog.

Run the focused resource check through the repository-controlled Godot entry:

```sh
bash scripts/quality/checks/godot_host.sh res://scripts/test/test_estate_asset_baseline.gd
```
