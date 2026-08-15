# scripts directory

> Chinese version: [`README_zh.md`](README_zh.md)

`scripts/` holds repo-level launch, build, quality-check and manual diagnosis
entry points. Both end users and contributors should prefer the stable entry
points at the repository root; do not bypass them to assemble your own runtime
environment.

## Scripts behind the stable entry points

| File | Category | Description |
| --- | --- | --- |
| `bootstrap.sh` | Dependency orchestration | Unified source-development/build preparation (Python, Node, frontend, Godot Web and Electron) |
| `elfienest.py` | CLI dispatcher | Called by `./elfienest.sh`; dispatches config, service lifecycle, Owner, database, migration and other commands |
| `serve.py` | Foreground service | Starts FastAPI, the engine and WebSockets; called by `serve` or background lifecycle commands |
| `build_godot_web.py` | Build | Exports and validates the Godot Web Runtime; final output goes to `build/components/godot-web/` |
| `release.py` | Release build | Assembles staging resources and invokes electron-builder |
| `check_quality_baseline.py` | Quality gate | Compares current Ruff, Ruff format and MyPy diagnostics against the controlled historical baseline |
| `check_quality_environment.py` | Quality preflight | Checks host capabilities required by repository-wide tests before the expensive full gate |
| `check_node_toolchain.sh` | Quality gate | Verifies the root Node.js/pnpm anchor and all independent Node project manifests |
| `architecture/app_layer_scan.py` | Architecture gate | Ratchets exact legacy App-layer violations and switches to deny-all after baseline removal |
| `architecture/system_layer_scan.py` | Architecture gate | Ratchets exact Elfie/Nest system-boundary violations and switches to deny-all after baseline removal |
| `architecture/check_governance_change.py` | Architecture gate | Separates governance from production changes and requires mirrored, versioned contract changes with an ADR |
| `architecture/contract_registry.py` | Architecture registry | Links each contract to its mirrors, ADRs, Agent rules, scanners, tests, conformance register and baseline |
| `__init__.py` | Package marker | Lets architecture tests import testable functions from scripts; not a command entry point |

### bootstrap.sh usage

`bootstrap.sh` is the unified dependency orchestrator and supports two tiers:

- `dev`: contributor tier — Python dev + frontend + Godot editor/Web export + Electron dev deps
- `build`: source/package-build tier — the release toolchain for the current native target

```bash
# Check dependency status
./scripts/bootstrap.sh check --tier=dev

# Ensure missing dependencies are installed
./scripts/bootstrap.sh ensure --tier=dev

# Print a JSON report (for CI)
./scripts/bootstrap.sh report --tier=build

# Verify the Node.js/pnpm declarations
bash scripts/check_node_toolchain.sh
```

### release.py usage

`release.py` is used for release packaging: it assembles staging resources and
invokes electron-builder:

```bash
# Build the current native target locally, without upload or publication
.venv/bin/python scripts/release.py --target darwin-x64

# Request the four-target coordination session; unavailable runners stay incomplete
.venv/bin/python scripts/release.py
```

For the complete native package set, use `.github/workflows/release.yml`:
`workflow_dispatch` keeps four validated installers as Actions artifacts, while
pushing a matching `v<version>` tag also publishes them as a GitHub Release.

Typical usage:

```bash
./elfienest.sh --help
./elfienest.sh serve
./elfienest.sh build-godot-web --check
./developer.sh build-godot-dedicated --check
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py
```

Before a repository-wide pytest run, probe the host once:

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_environment.py
```

Exit code `0` means loopback binding is available. Exit code `2` means the
current sandbox or host policy denied `127.0.0.1:0`; do not start the full
suite there. Run the same full command once in an environment that permits the
bind. Exit code `1` is an unexpected probe failure that needs diagnosis.

## Manual diagnosis scripts

The following scripts start components, hit local services or enter interactive
loops; they are not stable user commands available after install:

| File | Purpose & caveats |
| --- | --- |
| `chat_with_elfie.py` | Runs a long-lived engine loop and chats with the first persisted Elfie in the terminal; requires an adopted Elfie and a model runtime; cleans up services on manual exit |
| `e2e_dashboard_check.py` | Starts the configured model service with a temp directory and random ports to check the login, adoption and management dashboard flow; requires a configured model |
| `verify_nest_runtime_e2e.py` | Waits for a Godot Runtime and verifies two-Elfie sync, broadcast, semantic motion and cancel terminal states |

These scripts may take time, occupy ports or produce local data; they should
not be executed on import, and must not point at default production data without
explicit intent. Automatable regression should live under `test/e2e/` instead.

`verify_nest_runtime_e2e.py` starts the Python-side protocol v2 gateway; in
another terminal you need to launch `godot_project/main.tscn` against the
WebSocket address and nonce the script prints. The script uses only in-memory
state and never reads or writes the production `ELFIE_HOME`.

## Artifact boundaries

- All reproducible intermediate artifacts go into the root `build/`;
- Final installers go into the root `dist/`;
- Production data goes into `ELFIE_HOME`;
- Never write generated Godot Web, Desktop JavaScript, Python Core, logs or
  caches back into `scripts/` or any other source directory.

When you add a new script, make clear whether it is a stable entry point, a
build / quality gate, or a manual diagnosis tool, and update the corresponding
tests and Developer docs in lockstep.
