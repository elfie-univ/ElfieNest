# ElfieNest Godot source project

> 中文版：[`README_zh.md`](README_zh.md)

`godot_project/` is a standalone Godot source project that can be opened
directly by the Godot Editor. It is the single source of truth for the
ElfieNest 3D world, owning the house, geometry, coordinates, motion, collision,
characters and rendering. It is not a Python package and not a directory the
product runtime reads directly; the Python Core only exchanges in-nest events
and state through the selected exported Godot Runtime and its protocol, and must
never copy scene layouts or spatial facts from here.

## Current project

- Project file: `project.godot`
- Current engine feature version: Godot 4.7
- Main scene: `main.tscn`
- Renderer: GL Compatibility
- Web export preset: `Web` in `export_presets.cfg`

Main source layout:

```text
godot_project/
├── main.tscn, main.gd     # project entry
├── runtime/               # world configuration, actor sync and semantic action lifecycle
├── rooms/                 # Nest, rooms, layout and furniture assets
├── characters/            # Elfie characters, models, animation and appearance authoring material
├── ui/                    # observation UI
└── scripts/               # Godot-internal tests and asset authoring tools
```

Enter character authoring from [`characters/README.md`](characters/README.md);
enter room asset conventions from
[`rooms/assets/README.md`](rooms/assets/README.md).

## Editing safety

Before opening, running, debugging, screenshotting or closing Godot, you must
first follow the Godot operation gate in the public
[`AGENTS.md`](../AGENTS.md). If a local coding agent also has a safe-operation
skill available, follow the conditional routing in `AGENTS.md`:

1. Check existing Godot processes to avoid duplicate instances;
2. Verify the local Godot version against the one declared in `project.godot`;
3. On version mismatch, do not open the editable project without confirmation;
4. Check Git status before and after the operation; do not leave `.godot/`,
   import caches or unrelated `.import` noise behind.

Do not treat `godot_project/` as a generic script directory to be bulk
formatted, and never commit editor-generated artifacts as source.

## Web Runtime

End-user Observer clients use the exported Godot Web Runtime; they do not need
the Godot editor installed. The first phase is semantic and non-video; it does
not expose camera or JPEG-frame transport. Final artifacts may only go into:

```text
build/components/godot-web/
```

Build or check from the repository root:

```bash
GODOT_BIN=/path/to/godot4.7 ./developer.sh build-godot-web
./developer.sh build-godot-web --check
```

The builder verifies the engine version, checks required artifacts, generates a
hash manifest and replaces the official output on success. The Runtime artifact
contract can reference the same artifacts; do not keep copies inside
`godot_project/`, `app/interfaces/desktop/` or end-user web sources.

Environment preparation, directory layout and acceptance details for the Web
export are maintained only in [`WEB_EXPORT.md`](WEB_EXPORT.md) to avoid multiple
drifting copies of the flow.

## Linux Dedicated Runtime

The displayless authority runtime is a separate Linux x64 export. It contains
no browser payload and must only be written to:

```text
build/components/godot-linux-dedicated/
```

Build or check it from the repository root with a Godot 4.7 installation that
has the Linux x64 export template:

```bash
GODOT_BIN=/path/to/godot4.7 ./developer.sh build-godot-dedicated
./developer.sh build-godot-dedicated --check
```

The Dedicated preset forces Godot's `dedicated_server` feature and headless
execution. It is an authority host only; it does not create a display window or
upload JPEG camera frames.

## Runtime boundary with Python

The sole authority Runtime receives `configure_world`, `sync_actors`,
`execute_intent` and `cancel_intent` over the Gateway semantic protocol. The
Runtime lifecycle chooses one authority host: graphical Web, graphical Electron
authority role, or displayless Linux Dedicated. Godot is responsible for:

- Rebuilding fixed rooms based on the bed count and publishing a stable
  zone/anchor semantic catalog;
- Generating the navigation mesh, per-physics-frame pathfinding, collision and
  avoidance;
- Loading the fox / dog character models and playing movement, posture and
  facial animations;
- Computing tactile contacts and speech listeners and reporting typed events
  back with revision/generation.

Python never sends per-frame coordinates and never copies furniture occupancy
or collision geometry into `nest/`. A single
`execute_intent(intent="move_to_anchor")` can span multiple physics frames in
Godot; lifecycle events are only reported back on blocked, cancelled, timed-out
or final completion, so the Elfie's brain can keep deciding based on the real
outcome.
