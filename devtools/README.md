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

There are two entry points today:

| Tool | Real entry point | Local default | Purpose |
| --- | --- | --- | --- |
| Elfie Lab | `./developer.sh elfie-lab` | `127.0.0.1:9001` | Single-Elfie profile, perception, decision and turn debugging |
| Nest Lab | `./developer.sh nest-lab` | HTTP `127.0.0.1:9002`, Godot WS `127.0.0.1:9003` | Fixed rooms, temporary characters and Godot Runtime experiments |

The real App uses HTTP `8000`, Godot WebSocket `8765` and management WebSocket
`8766`, fully separated from the Lab default ports. When you run
`./developer.sh elfie-lab` or `./developer.sh nest-lab` directly, the launcher
first gracefully stops **the same-kind default Lab in the current workspace**,
waits for the port to be released, then starts and opens the new page; it never
deletes Lab data, never stops the real App, and never stops other projects or
unknown programs. If the default port belongs to an unknown process, the
command fails explicitly rather than force-killing it.

An explicit `--port` (and for Nest Lab also `--godot-ws-port`) keeps the
parallel-experiment semantics and the launcher will not reclaim old instances;
the Nest Lab WebSocket defaults to HTTP port + 1 and can also be specified
separately.

## Data isolation

The unified entry point stores web workbench data under independent
subdirectories of `${ELFIE_DEV_HOME:-~/.elfienest-dev}`. Providing an explicit
temporary directory for a single experiment makes cleanup easier:

```bash
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab --port 9001
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab --port 9002 --godot-ws-port 9003
```

Elfie Lab keeps its model connection and test Food in the isolated Lab data
root. In the page's experiment configuration, choose an installed local Ollama
model or enter an OpenAI-compatible URL, Token and model. Saving creates or
updates one test Food; the Lab does not preflight the connection, and the first
real turn makes the actual model call. Never copy any experiment data, key or
local configuration into Git-tracked files.

## Per-tool commands

Elfie Lab and Nest Lab are local FastAPI services that run until the process
exits:

```bash
./developer.sh elfie-lab --host 127.0.0.1 --port 9001
./developer.sh nest-lab --host 127.0.0.1 --port 9002 --godot-ws-port 9003
```

Both Elfie Lab and Nest Lab open a web page on startup and automatically reuse
or rebuild the same `build/components/godot-web/` export: it is re-exported only
when missing or when the Godot source has changed, never recompiled otherwise.
macOS auto-discovers standard Godot install locations; only set `--godot` or
`GODOT_BIN` when auto-discovery fails or multiple versions coexist. Each
browser launch uses a fresh local URL so that stale workspace page caches do
not shadow the new UI. Bed, temporary fox / dog, random walk, pause, resume and
reset all act only on the in-memory state of this one Lab process.

The two web workbenches share the React + TypeScript + Vite source in
`devtools/web/`; on startup they reuse or build `build/components/devtools-web/`
based on a source digest. To inspect that artifact on its own:

```bash
./developer.sh build-devtools-web --ensure
```

## Boundaries

- Do not modify or reuse `app/interfaces/web/static/` end-user pages;
- Do not hook tools into the production launch entry or end-user navigation;
- Do not run experiments against the production database, Owner sessions or
  default user data;
- Do not make `ElfieNestEngine`, Godot or product auth a mandatory dependency
  for single-module debugging;
- Tests for tool behavior live in mirrored paths under `test/devtools/`.
