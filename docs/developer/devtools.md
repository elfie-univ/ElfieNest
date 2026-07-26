# Developer Tools

## Entry points

The unified entry point is:

```bash
./developer.sh --help
```

The tools split into three mutually isolated workbenches:

| Tool | Entry point | Focus |
| --- | --- | --- |
| Elfie Lab | `./developer.sh elfie-lab` | A single Elfie's profile, perception, decisions and turns |
| Nest Lab | `./developer.sh nest-lab` | Fixed rooms, temporary characters, Godot events and semantic motion |
| Runtime Lab | `./developer.sh runtime-lab` | Providers, models, food, tools and safety |

They can reuse the underlying libraries and the same Godot Web Runtime, but they
must not depend on end-user auth, `ElfieNestEngine` or production data to start.
When launching Elfie Lab or Nest Lab, the Runtime is auto-checked; it is
re-exported only when missing or when the Godot source has changed.

The Elfie Lab and Nest Lab browser shells share the React + TypeScript + Vite
project in `devtools/web/`. The frontend artifact is generated only into
`build/components/devtools-web/` and never written back to or committed into
source directories; the launch command reuses or rebuilds it based on a frontend
source digest. The Nest Lab camera button only sends a restricted set of
intents — overview, activity area, dormitory, teleport room and reset view —
Godot remains the single source of truth for camera transforms.

Nest Lab embeds the exported fixed room in the browser. Developers can change
the bed count, add a fox / dog, start a Python-driven random walk that picks a
semantic anchor on a timer, or pause, resume and reset the experiment. Godot
handles geometry, rendering, pathfinding and collision; the Lab only sends v2
semantic commands and records Runtime facts. Both Labs use the same Godot Web
export as the real desktop run; each just provides an isolated web shell, data
root and local protocol entry.

Local ports are layered by convention: the real App uses `8000` / `8765` /
`8766`, Elfie Lab uses `9001`, Nest Lab uses `9002` / `9003`, and Runtime Lab
does not listen on a web port. Running the default Lab command again safely
restarts the old same-kind instance in the current workspace; only an explicit
port keeps parallel instances alive, and an unknown port occupant is never
terminated.

Elfie Lab ships an offline "mock food" by default on first launch, so you can
create an Elfie and validate the local flow; after configuring Ollama or a
remote provider, real foods automatically appear in the Runtime Lab selector.

## Data root

The three workbenches default to `${ELFIE_DEV_HOME:-~/.elfienest-dev}` and
write their own configuration, sessions and debug data under `elfie_lab/`,
`nest_lab/` and `runtime_lab/` respectively. They never default to
`${ELFIE_HOME:-~/.elfienest}`; if you explicitly pass the production root to
Elfie Lab's Runtime configuration, it is rejected. When a Runtime Lab
subprocess is needed, its dev root must also be explicitly passed as that
process's `ELFIE_HOME`.

Local acceptance can isolate both kinds of data at once:

```bash
ELFIE_HOME=/tmp/elfienest-production \
ELFIE_DEV_HOME=/tmp/elfienest-developer \
./developer.sh elfie-lab
```
