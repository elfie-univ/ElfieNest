# Debugging & workbenches

## Elfie Lab

For observing a single Elfie's profile, perception, cognitive turns and output
projection. It is one page of the shared Developer Tools service and is not
part of end-user navigation.

Its experiment configuration accepts either an installed local Ollama model or
an OpenAI-compatible URL, Token and model. Saving the form creates or updates
one Lab test Food. The Lab does not run a separate model or Food validation;
the first real turn is the connection attempt.

## Nest Lab

For validating in-nest state inside a fixed room, character entry, the Godot
semantic boundary and runtime events. On startup it auto-opens a local web
page: the center previews the exported Godot room; the right side lets you
adjust the bed count, add a fox or dog, start a Python-driven random walk, and
pause, resume or reset the experiment. The event timeline shows world
configuration, actor sync, motion terminal states, collisions and other Runtime
facts.

House geometry, rendering, pathfinding and collision are always performed by
Godot; the Lab does not copy coordinates or physics rules into Python. The
random walk is just Python picking a semantic anchor every two seconds and
sending an existing v2 move command — it is not the character's autonomous
brain. Just launch it; the script reuses the current export, or re-exports
using the Godot version declared by the project when missing or when the Godot
source has changed:

```bash
./developer.sh nest-lab
```

It does not silently start the real product engine; the Lab starts only the
isolated Godot Web Runtime and the corresponding local gateway. All three page
entry points share HTTP `127.0.0.1:9001`; Nest's Godot WebSocket is an internal
`9002` listener. When no port is passed, running any default command again
safely restarts the shared current-workspace service; an explicit `--port` is
treated as an independent experiment and does not reclaim the original
instance.

## Isolated runs

```bash
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab --port 9001
./developer.sh brain-eval --data-dir /tmp/elfienest-brain-eval --port 9001
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab --port 9001 --godot-ws-port 9002
```

Experiments must use a temporary `ELFIE_HOME` or an explicit data directory;
after debugging, check that no processes, ports, caches or generated files are
left behind.
