# Myelle authoring sources

> 中文版：[README_zh.md](README_zh.md)

- `myelle-concept-reference.png`: user-provided orange character reference.
- `myelle-tail-corrected.blend`: Mixamo-compatible model with `Tail_01` through
  `Tail_04`, normalized tail weights and an embedded source texture.
- Input: the user-provided `base_basic_shaded (2).fbx`, received on 2026-10-02.
- Authoring tool: Blender 5.2.0 LTS. Runtime model: `../myelle.glb`.

The GLB applies the armature object's rotation, exports no actions, and uses
the shaded texture as PBR albedo rather than emission. Runtime actions are
shared from `characters/animation/`. The original FBX remains unchanged.

Image/3D generation provider, model version, generation date and redistribution
license were not supplied and must be confirmed before redistribution. This
source directory is excluded from Godot imports and release exports.
