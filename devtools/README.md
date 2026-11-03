# ElfieNest Developer Tools

> 中文版：[`README_zh.md`](README_zh.md)

`devtools/` are module workbenches isolated from the end-user product. They are
not exposed through user navigation or as production service entry points, and
they must not depend on end-user pages to work.

## Unified entry point

Prepare the repo-pinned Python environment first, then list the available
tools:

```bash
./elfienest.sh version
./developer.sh --help
```

The three experiment entry points launch the unified Developer Tools HTTP service.
The independent asset design command serves only the approved asset workbench:

| Command | Initial page | Local default | Purpose |
| --- | --- | --- | --- |
| `./developer.sh elfie-lab` | `/elfie/experiment` | HTTP `127.0.0.1:9001` | Single-Elfie experiments |
| `./developer.sh brain-eval` | `/elfie/evaluations` | same | Batch evaluation and reports |
| `./developer.sh nest-lab` | `/nest/experiment` | same (internal Godot WS `9002`) | Nest and Godot Runtime experiments |
| `./developer.sh asset-design` | `/assets/design` | HTTP `127.0.0.1:9001` | Independent room and furniture asset preview |

Asset design preserves the approved asset library and complete right-hand 3D control
panel. Its source is `devtools/asset_design/web/`; it reads registered models,
measurements and images from `build/asset_previews/catalog.json`. New asset versions
reuse this viewer instead of generating HTML pages. It does not start experiment
state or Godot, and does not build their frontends. Open this independent page
with `./developer.sh asset-design`; it is not mounted in the experiment service
or its menus. Layout baselines and read-only boundary tests live in
`test/devtools/asset_design/`. Missing local asset
data leaves an empty workbench; Git preserves the tool, not the large design files.

Preview content selects the model, separate components or saved images. Object and
floor selection live only in the viewer; available floors come from model tags.
Houses can be viewed together. Object, floor, section, display switches, lighting
and camera preset are saved in the URL. Camera controls do not change those
selections; the four M01-specific sample shortcuts have been removed.

`./developer.sh brain-trace` is a backend-only collector and never starts a web page. `list`
shows Elfies and saved Foods in an isolated Lab data root. `collect` runs a message sequence through
the same production Brain chain and writes model calls, Memory recall, Context, Reasoning, Decision,
Receipt, Settlement, state diffs and persistence evidence to `build/brain-trace/<run-id>/`. Model and
Memory edges are independently selectable as `real` or `mock`: real Memory always runs on an Elfie
snapshot clone, while mock Memory uses the real Memory algorithms with a typed fixture. The collector
only records data; it does not analyze, score or diagnose the run and never mutates the source Elfie.

```bash
./developer.sh brain-trace list --data-dir /tmp/elfienest-devtools
./developer.sh brain-trace collect \
  --data-dir /tmp/elfienest-devtools \
  --elfie-id <elfie-id> \
  --memory real --model mock \
  --messages-file messages.jsonl
```

The real App uses HTTP `8000`, Godot WebSocket `8765` and management WebSocket
`8766`, fully separated from the Lab default port. All three commands launch
the same HTTP service. The launcher first gracefully stops **the current
workspace's default Developer Tools instance**, waits for the port to be released,
then starts and opens the requested page; it never
deletes Lab data, never stops the real App, and never stops other projects or
unknown programs. If the default port belongs to an unknown process, the
command fails explicitly rather than force-killing it.

An explicit `--port` (and for Nest Lab also `--godot-ws-port`) is reserved for
diagnostic parallel instances. The Nest WebSocket defaults to HTTP port + 1 and
is an internal runtime connection, not a second web page.

## Data isolation

The unified entry point stores web workbench data under independent
subdirectories of `${ELFIE_DEV_HOME:-~/.elfienest-dev}`. Without `--data-dir`,
the Elfie library honors Elfie Lab's existing `ELFIE_LAB_DATA_DIR` override;
all three pages share that same storage instance. An explicit `--data-dir`
still overrides the default root. Providing an explicit
temporary directory for a single experiment makes cleanup easier:

```bash
./developer.sh elfie-lab --data-dir /tmp/elfienest-devtools --port 9001
```

Elfie Lab keeps its Foods and dedicated model connections in the isolated Lab
data root. The Food form has two explicit connection choices. **Local Ollama**
uses `http://127.0.0.1:11434` by default, performs one explicit health probe,
never scans ports, and does not ask for an API key; an advanced control can
override the loopback address and port. **Custom OpenAI-compatible endpoint**
accepts an API URL and an optional API key, so a private no-auth deployment also
works. Model IDs and Food role assignments remain explicit in both modes. A
failed model smoke request is shown in place and nothing is persisted. Editing
a Food can change its name, model list and role assignments, while its saved
connection type, URL and credential state remain read-only. Never copy any
experiment data, key or local configuration into Git-tracked files.

Elfie Lab also has a separate full-page **Batch evaluation** workspace. Its global table
stores one immutable report per execution, groups paired A/B reports under expandable rows,
and opens single-report or comparison evidence in a wide right drawer. Quick runs 3
scenarios and Standard runs 8. A paired Food run clones one frozen Elfie snapshot for both
candidates; report comparisons explicitly distinguish strict, observational, and
incompatible conditions. These presets are exploratory and do not require a Godot
evaluation scenario. See the
[Brain evaluation workflow](../docs/developer/engineering/brain-evaluation.md#11-daily-feedback-in-elfie-lab)
for the exact loop and the boundary between Lab feedback and formal promotion evidence.

## Three entry points

The local FastAPI service runs until the process exits. For normal use, run one
of these no-argument commands:

```bash
./developer.sh elfie-lab
./developer.sh brain-eval
./developer.sh nest-lab
```

One service provides three same-origin stable addresses:
`http://127.0.0.1:9001/elfie/experiment` (single-Elfie experiment),
`http://127.0.0.1:9001/elfie/evaluations` (batch evaluation), and
`http://127.0.0.1:9001/nest/experiment` (Nest experiment). The narrow left
navigation switches between them, and refreshing an address keeps the current
page. The batch list, single report, and comparison report remain list/drawer
states inside the batch page rather than becoming separate top-level pages.

All three entry points open a web page on startup and automatically reuse
or rebuild the same `build/components/godot-web/` export: it is re-exported only
when missing or when the Godot source has changed, never recompiled otherwise.
macOS auto-discovers standard Godot install locations; only set `--godot` or
`GODOT_BIN` when auto-discovery fails or multiple versions coexist. Each
browser launch uses a fresh local URL so that stale workspace page caches do
not shadow the new UI. Bed assignment, random walk, pause, resume and reset act
only on this process's scene state. Newly created Elfies are saved in the shared
experiment library and can be reused after restarts.

Nest Lab opens a full-height estate monitor with one full-width cascade toolbar.
The first dropdown selects View or Action; subsequent dropdowns depend on that
selection and are separated by `>`. Only the middle control area scrolls on narrow
screens. Time/lighting, Play/Pause and Run log remain on the right. Play/Pause toggles
automatic wandering; Run log toggles a translucent panel without resizing the monitor.
The lighting selector offers Live, Day, Evening and Late night. Selectors fit their
current label; longer entries can wrap in independently sized popup menus.

View offers fixed cameras (with Reset) or Elfie view (actor, then follow/first-person).
Follow orbit keeps lens clearance from geometry and limits its height and distance
around the selected actor. Live lighting keeps evening lights on until midnight;
quiet hours run from 00:00 to 06:00 in local time.
There is no frame-freeze control. Both View and Elfie actions share the selected actor
and the same picker, whose last entry opens Manage Elfies.
In unified Developer Tools, Nest Lab automatically reads saved Elfies from the
single-Elfie experiment under the same data root, reusing their IDs, names and
resolved appearances after service restarts (up to 32 actors in the scene).
Newly saved Elfies appear on the next list refresh. Removing a saved Elfie only
removes it from the scene; its source profile is never deleted or regenerated.
Restarting the service reloads the saved actors.
The dialog creates and saves experiment Elfies using an optional name, species,
age and sex through Elfie Lab's existing creation and storage flow. Both pages
reuse the resulting ID, profile and appearance across refreshes and restarts.
The default uses the global Developer data root; `--data-dir` selects a local
root without copying or merging the two libraries. Age bounds follow Genesis
creation policy. Resetting the scene or removing an actor preserves its profile.

Actions, positions, fixed cameras, scene objects and demonstrations use two-level
cascaders. Clicking a category opens the second column; only selecting a leaf triggers
the operation. Search matches category or item names. Compact controls display only
the selected leaf; short menus such as lighting and perspective remain ordinary dropdowns.
Fixed cameras and action positions pair each bedroom and its terrace under the same
M-number category, with the bedroom and terrace adjacent in the camera submenu.

Elfie actions use one grouped action selector and, when needed, one position selector
grouped by scene. Selecting a clip or final position submits it directly and switches
to that actor's follow camera, as do combinations and door passages, without Execute
or Stop buttons. Switching cancels the old command and starts the latest
selection after its terminal acknowledgement; rapid selections replace pending work.
Lab previews may use any bed without changing home ownership. Single furniture previews
relocate to the Runtime's target approach before playing the action. One position selector
groups paired bedrooms/terraces, central floors and outdoor furniture; random selection displays
the actual chosen position. The central sofa has three independent contacts with exclusive
occupancy, and outdoor benches use the production sitting and standing transitions.
Scene controls offer each door's open, close and automatic modes, retaining anti-crush
collision checks. Automatic mode demonstrates a passage when an actor is selected.
Fountain and lake playback have independent clocks. One grouped demonstration selector
offers morning and evening routines, the building ring, forest trail, lakeside platform,
top-floor arrival with a wave, and sofa-seat inspection. Runtime geometry and navigation
determine routes; disconnected routes are disabled with a reason. Selecting a new actor
action cancels the running demonstration. Time/lighting
provides live/day/evening/late-night preview independently of camera and actor actions.
Manual actor actions resume a paused simulation and take over automatic wandering;
Run log shows actual command results. The workbench does not implement animation,
navigation, furniture or water effects. World controls stay disabled when Runtime
configuration fails.

The three pages share the React + TypeScript + Vite source in
`devtools/web/`; on startup they reuse or build `build/components/devtools-web/`
based on a source digest. To inspect that artifact on its own:

```bash
./developer.sh build-devtools-web --ensure
```

Brain Eval's explicit `catalog`, `capture`, `compare` and `calibrate` actions remain
available for artifact workflows; without an action it only opens the batch page.
Those explicit actions run real Brain wiring inside disposable Elfie Lab state,
write artifacts only to `build/brain-eval/<run-id>/`, and do not open a web port. Start with
the [Brain evaluation workflow](../docs/developer/engineering/brain-evaluation.md); a
cataloged scenario family is not considered automated until its Fixture, event/fault
adapter, success rule, and evidence path exist.

## Boundaries

- Do not modify or reuse `app/interfaces/web/static/` end-user pages;
- Do not hook tools into the production launch entry or end-user navigation;
- Do not run experiments against the production database, Owner sessions or
  default user data;
- Do not make `ElfieNestEngine`, Godot or product auth a mandatory dependency
  for single-module debugging;
- Do not let Brain Eval read production `ELFIE_HOME`, write outside `build/brain-eval/`,
  or turn an uncalibrated Judge into an automatic promotion;
- Tests for tool behavior live in mirrored paths under `test/devtools/`.

The Elfie action dropdown exposes complete sit/stand and sleep/wake cycles without
separate sleep-pose menus. The runtime retains back/left/right sleep animations as
named `furniture_cycle` variants of the authenticated `use_anchor` command, with
target validation and cancellation. Lab previews do not change home ownership. The
production implementations live under `godot_project/runtime/actor/`; the Lab
contains only controls and camera observation. The three sofa contacts are estate
metadata, not animation-specific duplicate scenes. A cycle failure remains visible
in Run log; a matching source animation alone does not establish furniture fit.
