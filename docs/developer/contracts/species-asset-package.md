# Species asset package contract

Status: normative, version 1

This contract defines when a species is a usable ElfieNest runtime species. A
species is not selectable because a name, profile, portrait, or placeholder
scene exists. It is selectable only when its complete Godot asset package is
present and the runtime validator accepts it.

## Package layout

Every runtime species owns one directory under `godot_project/characters/`:

```text
<species_id>/
├── <species_id>.glb
├── <species_id>.tscn
└── species_manifest.json
```
The package must contain all of the following:

- A production `.glb` with a non-empty visible mesh and a `Skeleton3D`.
- A `<species_id>.tscn` whose root is `CharacterBody3D`, whose `species_id`
  property matches the directory, and which uses the production `.glb`.
- `VisualRoot`, `VisualRoot/character`, `AnimationPlayer`, and
  `CollisionShape3D` nodes.
- The shared `ElfieActor` movement/appearance runtime and a usable main
  collision shape.
- Portrait and preview capability implemented by the real runtime appearance
  path. A static SVG or other fallback image is not a valid substitute.
- Every required shared animation source and every required animation name:
  `idle`, `walking`, `running`, `jump`, `twist_dance`, `left_strafe`,
  `left_strafe_walking`, `left_turn`, `left_turn_90`, `right_strafe`,
  `right_strafe_walking`, `right_turn`, and `right_turn_90`.

## Manifest

`species_manifest.json` is the machine-readable declaration for the package.
It must use `schema_version: 1` and include:

- `species_id`, `scene_file`, and `model_file`;
- `required_nodes` containing the four required node paths above;
- `required_capabilities` containing `movement`, `appearance`, `portrait`, and
  `preview`;
- `required_animations` containing every animation name above; and
- `shared_animation_files`, mapping every required animation name to an
  existing `res://characters/animation/...` resource.

The manifest is checked against the loaded scene, referenced model, imported
resources, node tree, mesh, skeleton, and animation sources. A malformed or
incomplete package is rejected and omitted from the discovered actor catalog;
it must not be made selectable by a frontend fallback.

## Registration and acceptance

Adding a species requires the complete package, a matching domain canon and
registry entry, and tests for both the Python registry and Godot catalog. The
domain registry may mark a species runtime-supported only after the package
passes this contract. The frontend reads the API's active species list and does
not maintain a second species list or image fallback.

The canonical verification commands are:

```sh
uv run --no-sync pytest -q \
  test/elfie/profile/test_species_registry.py \
  test/app/features/adoption/test_facade.py
godot --headless --path godot_project \
  --script scripts/test/test_species_catalog.gd
```
