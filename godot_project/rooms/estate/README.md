# Estate visual asset baseline

> 中文：[`README_zh.md`](README_zh.md)

Open `res://rooms/estate/estate.tscn` in the repository's Godot 4.7 project.
It contains one central building and eight separately addressable house instances
(`M01`–`M08`), all using the single `pod.glb` resource. This scene is not connected
to `main.tscn` or the existing Runtime.

| Resource | Snapshot | Size |
| --- | --- | --- |
| `central.glb` | Current floors 1–3 furniture trial, original fourth floor and architecture | 69,420,928 bytes |
| `pod.glb` | Confirmed complete house 02, including its four furniture sets | 39,715,472 bytes |

The central building is a development snapshot, not an approved final design.
The house shell and ground-floor furnishings match the confirmed source;
existing terrace props are retained without claiming a separate terrace approval.
Collision, navigation, interaction logic and animated water are not included.
The outdoor garden is excluded. Blender sources, reference images, previous
versions, unused scene data and import caches are excluded.

Both GLBs embed their textures. No files from `build/asset_previews/` are needed
to load the committed scene. `manifest.json` records source versions, SHA-256
hashes and byte-preservation checks. This export does not simplify geometry or
merge independent furniture parts. Functional and floor tags remain intact.

Coordinates use metres and glTF's right-handed Y-up basis. `central.glb` retains
the original world coordinates. `pod.glb` has an inverse source-anchor wrapper
that places the house in its reusable local frame. `placements.json` stores
the eight original anchor matrices in column-major order. `estate.tscn` applies
those matrices directly; do not translate or rotate the GLB a second time.
Descendant house tags retain source module `M01`; use each scene instance's
`metadata/module` (`M01`–`M08`) to distinguish the independently placed houses.

Run the focused resource check through the repository-controlled Godot entry:

```sh
bash scripts/quality/checks/godot_host.sh res://scripts/test/test_estate_asset_baseline.gd
```
