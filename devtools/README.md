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

There are three no-argument entry points. They launch the same Developer Tools
HTTP service; the command only selects the initial page:

| Command | Initial page | Local default | Purpose |
| --- | --- | --- | --- |
| `./developer.sh elfie-lab` | `/elfie/experiment` | HTTP `127.0.0.1:9001` | Single-Elfie experiments |
| `./developer.sh brain-eval` | `/elfie/evaluations` | same | Batch evaluation and reports |
| `./developer.sh nest-lab` | `/nest/experiment` | same (internal Godot WS `9002`) | Nest and Godot Runtime experiments |

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
subdirectories of `${ELFIE_DEV_HOME:-~/.elfienest-dev}`. Providing an explicit
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
not shadow the new UI. Bed, temporary fox / dog, random walk, pause, resume and
reset all act only on the in-memory state of this one Lab process.

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
