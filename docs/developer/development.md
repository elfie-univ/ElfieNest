# Development flow

This page covers the standard development path from preparing the environment
to finishing local verification. The specific CLI, Godot and Desktop commands
live in [Commands & dev tools](./tooling); the collaboration policy follows the
[Contributing guide](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md).

## Prepare the locked environment

The project is pinned to CPython `3.9.25`, with dependencies pinned by
`uv.lock`:

```bash
./install.sh --env-only
uv sync --locked --extra dev
uv lock --check
```

Do not write your own `pip install` flow, and do not edit the lockfile to work
around a local environment issue. The installer supports user-level
installation only — never use `root` or `sudo`.

Unless the maintainer explicitly approves a full-repo upgrade, CPython `3.9.25`
is an immutable contract: do not modify version files, lockfiles, CI or launch
scripts because of the local default interpreter, a single dependency or a
local feature. All agents, developers and automation may only use `uv` and the
repo's `.venv/bin/python3`; do not call system `python` / `python3`, other
virtual environments, or an `ELFIENEST_PYTHON` override. When the environment
is wrong, run `./install.sh --env-only` and then run the locked commands with
`uv run --no-sync`.

## Pick a test layer

The test directory mirrors the source boundaries. Run the tests closest to your
change first, then widen the verification scope:

```bash
# Example: only changed the cognitive coordinator
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/elfie/brain/test_coordinator.py

# Required for any cross-module or directory-boundary change
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/

# When you need full regression
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/
```

`test/architecture/` guards against legacy top-level packages, illegal reverse
dependencies, root-level test files and engineering-config regressions. For the
full directory and marker reference see the
[test README](https://github.com/elfie-univ/ElfieNest/blob/main/test/README.md).

## Run the quality gate

The repo currently carries a set of historical Ruff and MyPy diagnostics
recorded by hash. The unified quality gate lets the historical set live on but
blocks any new diagnostic:

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py

PRE_COMMIT_HOME=/tmp/elfienest-precommit \
  uv run --no-sync pre-commit run --all-files
```

pre-commit and CI also run Gitleaks. Do not bypass the secret check with
`--no-verify`, and do not update the quality baseline for your own new issues;
fix the diagnostics you introduced.

## Debug a single module

The three workbenches are all isolated from the end-user product:

```bash
./developer.sh elfie-lab \
  --data-dir /tmp/elfienest-elfie-lab --port 9001

./developer.sh nest-lab \
  --data-dir /tmp/elfienest-nest-lab --port 9002

./developer.sh runtime-lab \
  --config-dir /tmp/elfienest-runtime-lab show
```

- Elfie Lab inspects a single Elfie's profile, perception, decisions and turns;
- Nest Lab starts an isolated Nest, an independent Godot v2 gateway and an
  optional browser room preview; it does not start `ElfieNestEngine` and does
  not read production data;
- Runtime Lab inspects providers, model configuration and connections and does
  not listen on a port.

The default ports are only local development values. Do not wire the
workbenches into end-user navigation, and do not let them use default
production data. The real App uses `8000` / `8765` / `8766`, Elfie Lab uses
`9001`, Nest Lab uses `9002` / `9003`. Launching the same default Lab safely
restarts the old instance in the current workspace; explicit ports are for
parallel experiments and do not terminate existing instances. For the detailed
boundaries see the
[Devtools README](https://github.com/elfie-univ/ElfieNest/blob/main/devtools/README.md).

## Product Web and LAN mode

The Core serves four same-origin pages: `/setup` for local first-run, plus
`/login`, `/chat` and `/manage`. The first Owner can only be created through
the local or Electron loopback service; afterwards, devices on the same network
segment go straight to the login page. Regular users always land on the chat
page, and `/manage` server-redirects to `/chat`. The Owner lands on the
management page by default and may switch their own default page to chat.

The chat page uses the same-session authentication as REST over the same-origin
`/api/v1/ws/chat`. User messages get real-time confirmation; Elfie replies
produced by the runtime are written into chat history first and then bridged to
the same-origin chat connection of the owning user, so history and real-time
messages stay consistent after refresh.

`/manage` is the only Owner management page and covers monitoring, global
read-only Elfie filtering, Elfie nest beds/slots, users, providers, models,
tools, food, runtime logs, system settings and Godot status. Chat, adoption and
private personal Elfie profiles belong only to `/chat`; the management page has
no user–Elfie ownership assignment entry.

The frontend source lives in `app/interfaces/web/frontend/`, and its build
output may only go into the root `build/web/`:

```bash
cd app/interfaces/web/frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build
```

In development the default listens only on loopback; to expose the login page
to other devices on the LAN, use `--lan` explicitly. LAN does not relax
account, role, CSRF, Host/Origin or device credential checks. The installed CLI
can turn off the home LAN service with `--loopback`. Devices use only Bearer
credentials on `/api/v1/ws/devices`; browser users always use session cookies.

`/api/v1/ws/devices` does not accept free-form JSON: every text frame is capped
at 64 KiB and may only be `heartbeat`, `sensor_event`, `receipt` or
`command_poll`. Sensor events and action receipts directly reuse the type
contracts from `elfie.body.contracts`; the Core queues actions into the next
`command_poll` of a connected device through `DeviceGatewayTransport`. Device
credentials are shown only once, at registration or rotation, and must never be
written into browser logs, test fixtures or the repository.

The current product acceptance focuses on `/setup`, `/login`, `/chat`,
`/manage`, the Electron login entry and mobile browsers. Owner configuration of
the device–embodiment lease–capability claim, device throttling policy and the
real-installer staging / dual-client automation remain in phase two; the legacy
single-page console has been retired.

## Pre-commit checks

Before delivering a change set, confirm at least:

1. The tests directly corresponding to the change pass;
2. `test/architecture/` passes;
3. The unified quality gate and pre-commit pass;
4. When docs are changed, VitePress builds cleanly;
5. There are no real keys, local absolute paths, caches or build artifacts;
6. README, architecture docs and tests stay in sync after adding directories or
   cross-boundary dependencies.

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

For PR scope, test evidence and review requirements see the
[Contributing guide](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md)
and the
[PR template](https://github.com/elfie-univ/ElfieNest/blob/main/.github/pull_request_template.md).

## Common issues

### uv or Ruff cache is not writable

Put the cache in a temporary directory; do not delete the repo or user data:

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/
```

### A test read day-to-day data

Stop the test immediately and give it an isolated `ELFIE_HOME` or pytest
`tmp_path`. Tests, doc acceptance and workbenches should never read
`~/.elfienest/` by default.

### Godot will not open or version mismatches

Do not open the editable project yet. Read the
[Godot README](https://github.com/elfie-univ/ElfieNest/blob/main/godot_project/README.md),
check existing Godot processes, the project-declared version and the Export
Templates, then follow the public operation gate.

### The quality gate reports historical issues

Distinguish `existing`, `resolved` and `new` first. Only `new` blocks the
current change; do not hide it by writing a new baseline.
