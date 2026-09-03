# Developer Tools

## Entry points

The unified entry point is:

```bash
./developer.sh --help
```

The tools provide three page entry points backed by one same-origin HTTP service:

| Command | Initial page | Focus |
| --- | --- | --- |
| `./developer.sh elfie-lab` | `/elfie/experiment` | A single Elfie's profile, perception, decisions and turns |
| `./developer.sh brain-eval` | `/elfie/evaluations` | Batch evaluation and reports |
| `./developer.sh nest-lab` | `/nest/experiment` | Fixed rooms, temporary characters, Godot events and semantic motion |

They can reuse the underlying libraries and the same Godot Web Runtime, but they
must not depend on end-user auth, `ElfieNestEngine` or production data to start.
When launching any page, the Runtime is auto-checked; it is
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
