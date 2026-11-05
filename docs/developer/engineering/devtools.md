# Developer Tools

## Entry points

The unified entry point is:

```bash
./developer.sh --help
```

The experiment pages share one HTTP service:

| Command | Initial page | Focus |
| --- | --- | --- |
| `./developer.sh elfie-lab` | `/elfie/experiment` | A single Elfie's profile, perception, decisions and turns |
| `./developer.sh brain-eval` | `/elfie/evaluations` | Batch evaluation and reports |
| `./developer.sh nest-lab` | `/nest/experiment` | Fixed rooms, temporary characters, Godot events and semantic motion |

Asset previews use Nest Lab (`./developer.sh nest-lab`, `/nest/experiment`).
The independent `/assets/design` page, design workspace and offline asset CLI have
been removed. Future asset authoring uses the existing formal GLB resources,
sidecar metadata, scenes and scripts in `godot_project/`; preview changes through
Nest Lab using those same formal resources.

They can reuse the underlying libraries and the same Godot Web Runtime, but they
must not depend on end-user auth, `ElfieNestEngine` or production data to start.
When launching an experiment page, the Runtime is auto-checked; it is
re-exported only when missing or when the Godot source has changed.

The Elfie Lab and Nest Lab browser shells share the React + TypeScript + Vite
project in `devtools/web/`. The frontend artifact is generated only into
`build/components/devtools-web/` and never written back to or committed into
source directories; the launch command reuses or rebuilds it based on a frontend
source digest. Nest Lab sends restricted semantic intents; Godot remains the single source of truth for camera transforms.

Nest Lab embeds the exported fixed room in the browser. The room always exposes
32 fixed beds; developers can add a saevi / tovren, start a Python-driven random walk that picks a
semantic anchor on a timer, or pause, resume and reset the experiment. Godot
handles geometry, rendering, pathfinding and collision; the Lab only sends v2
semantic commands and records Runtime facts. Both Labs use the same Godot Web
export as the real desktop run; each just provides an isolated web shell, data
root and local protocol entry.

Local ports are layered by convention: the real App uses `8000` / `8765`, while
Developer Tools exposes one HTTP port at `127.0.0.1:9001`. Running any default
Developer Tool command again safely restarts the current workspace instance; the
Nest page's Godot WebSocket is an internal `9002` listener and is not a second
web page. Only an explicit port keeps parallel instances alive, and an unknown
port occupant is never terminated.

Elfie Lab reads the isolated Runtime `nest.db` food catalog on first launch.
The database seeds the two system rows, which appear as unconfigured until
Ollama or an OpenAI-compatible provider is configured in the page; no synthetic
food row is injected. The configuration form only saves the selected model and
connection. The first real turn is the model connection attempt.

## Asset consolidation

Apply these principles to furniture, rooms and complete buildings:

- Group by independent function, movement and visibility, rather than by colour or
  construction detail. Combine static parts that always operate together; preserve
  separate doors, drawers, controllable lights, building modules and floor visibility.
- Keep bed shells, mattresses, duvets and individual pillows independent. Bindings,
  seams and fixed decorative fittings belong to their owning item.
- Different colours and surface properties can share a mesh through vertex colours
  and PBR texture atlases. Preserve colour, roughness, metalness, normals, emission,
  texture repeat and padding; do not silently flatten every surface to one material.
- Count functional components, mesh objects, material primitives and triangles
  separately. A parent group or a mesh with several materials does not by itself
  reduce draw batches. Transmission or transparency may require separate batches.
- Consolidate groups before any separately approved triangle reduction. Preserve
  positions, dimensions, normals, topology, animation ownership and viewer tags.
- Keep the approved baseline and derive a new local version. Verify geometry,
  material/texture mapping and independent parts, then compare both versions using
  the same camera and lighting in Nest Lab.
- Record measured counts, appearance changes and texture-memory costs in the asset's
  verification output. Fewer batches alone do not establish faster interaction.

## Data root

The unified interactive service defaults to `${ELFIE_DEV_HOME:-~/.elfienest-dev}` and
write their own configuration, sessions and debug data under `elfie_lab/` and
`nest_lab/`. They never default to `${ELFIE_HOME:-~/.elfienest}`; if you
explicitly pass the production root to Elfie Lab's Runtime configuration, it
is rejected.

Brain Eval creates disposable Runtime state for capture and writes only regenerable
artifacts under `build/brain-eval/<run-id>/`. It rejects production `ELFIE_HOME` and output
paths outside that build tree. Its design and exact batch workflow are documented in
[Elfie Brain evaluation and evolution system](../designs/elfie/brain/elfie-brain-evaluation-system)
and [Brain evaluation workflow](./brain-evaluation).

Local acceptance can isolate both kinds of data at once:

```bash
ELFIE_HOME=/tmp/elfienest-production \
ELFIE_DEV_HOME=/tmp/elfienest-developer \
./developer.sh brain-eval
```
