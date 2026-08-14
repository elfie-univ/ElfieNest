# Character assets

> 中文版：[`README_zh.md`](README_zh.md)

`godot_project/characters/` holds reusable species models, shared animations
and the character runtime scripts. Rooms, furniture, cameras and character
assets are kept separate.

Character assets only define species appearance and embodiment — they are not a
complete Elfie identity. An Elfie's species, appearance, personality,
capabilities, memory and runtime state belong to `elfie/`; the current
responsibility boundary is documented in the
[Elfie module guide](../../elfie/README.md) and the
[Developer architecture doc](../../docs/developer/architecture/index.md).

## Current structure

```text
characters/
├── animation/              # Mixamo public bipedal animation library
├── shared/
│   └── elfie_actor.gd      # movement, animation loading and adaptive main collider
├── dog/
│   ├── dog.glb
│   └── dog.tscn
├── fox/
│   ├── fox.glb
│   └── fox.tscn
├── cat/
│   └── cat.tscn              # Myelle procedural visual v0.1
├── CHARACTER_CREATION_GUIDE.md
├── BLENDER_APPEARANCE_AUTHORING_GUIDE.md
└── APPEARANCE_SYSTEM_SPEC.md
```

Saevi (fox), Tovren (dog), and Myelle (cat) are the current selectable species.
Myelle's first runtime visual is a code-native, reusable scene while the
production cat asset is being authored; it still uses the same actor, collision,
appearance, and animation-name contracts. At runtime the scene is selected by
`species`; when older data has no `species`, the existing stable fallback is
preserved.

## Runtime collision principles

- The `CharacterBody3D` main capsule handles ground movement and wall/doorframe
  blocking;
- The main capsule scales with `height`, `build` or numeric appearance
  parameters;
- Arms, legs and tails do not participate in everyday movement blocking, so
  animated actions do not get the character stuck against walls;
- Skeletal hitboxes are used only for touch, hit detection or ragdoll and must
  use a dedicated collision layer;
- Visual clipping of hands and feet against walls is handled by IK and action
  constraints, not by complex movement colliders.

## Asset boundaries

- Species-shared assets are stored only once; never copy GLBs, animations or
  textures per Elfie;
- Per-individual differences are described by appearance data keyed on
  `elfie_id` and never written back into shared assets;
- A new species must provide its own thin-wrapper scene and reuse
  `shared/elfie_actor.gd`;
- Public bipedal animations may only be added to `animation/` after passing
  validation against the unified skeleton mapping;
- Quadruped forms will be added as an independent locomotion asset in the
  future and are not enabled at runtime today.

The full production flow and acceptance checklist live in the
[Character creation and integration guide](CHARACTER_CREATION_GUIDE.md).
Appearance parameters, Blender shape keys, species configuration and
random-generation constraints are in the
[Appearance parameter and species master spec](APPEARANCE_SYSTEM_SPEC.md). When
you actually author production regions, bone proportions, shape keys and fur
color masks, follow the
[Blender animal appearance master authoring guide](BLENDER_APPEARANCE_AUTHORING_GUIDE.md)
step by step.
