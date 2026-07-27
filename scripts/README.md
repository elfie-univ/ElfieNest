# scripts directory

> 中文版：[`README_zh.md`](README_zh.md)

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
| `elfienest_install_helpers.sh` | Shell library | Used by `install.sh` to validate the user-level install directory and PATH; not standalone-executable |
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

Typical usage:

```bash
./elfienest.sh --help
./elfienest.sh serve --fallback
./elfienest.sh build-godot-web --check
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py
```

## Manual diagnosis scripts

The following scripts start components, hit local services or enter interactive
loops; they are not stable user commands available after install:

| File | Purpose & caveats |
| --- | --- |
| `chat_with_elfie.py` | Runs a long-lived engine loop and chats in the terminal; needs a model runtime; cleans up services on manual exit |
| `e2e_dashboard_check.py` | Starts a fallback service with a temp directory and random ports to check the login, adoption and management dashboard flow |
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
