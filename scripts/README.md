# scripts directory

> Chinese version: [`README_zh.md`](README_zh.md)

`scripts/` holds repo-level launch, build, quality-check and manual diagnosis
entry points. Both end users and contributors should prefer the stable entry
points at the repository root; do not bypass them to assemble your own runtime
environment.

## Layout and stability contract

The root keeps stable command or import paths that are referenced by launchers,
CI, release automation or production bootstrap. These paths do not move during
internal cleanup:

| Stable root path | Category | Owner / caller |
| --- | --- | --- |
| `bootstrap.sh` | Bootstrap entry | Source-development and build dependency orchestration |
| `elfienest.py` | CLI dispatch | Called only through `./elfienest.sh` and packaged launchers |
| `serve.py` | Runtime entry | Foreground service and managed lifecycle startup |
| `pre_submit_gate.sh` | Quality entry | Explicit local commit/push/full diagnostic checkpoint |
| `check_node_toolchain.sh` | Quality entry | Node.js and pnpm manifest consistency |
| `check_quality_baseline.py` | Quality entry | Ruff, format and MyPy baseline |
| `check_quality_environment.py` | Quality entry | Host capability preflight for broad tests |
| `check_release_version.py` | Release quality entry | Repository and package version consistency |
| `godot_host_validate.sh` | Godot quality entry | Controlled host-side Godot validation |
| `godot_species_validation.py` | Runtime/build module | Shared species validation injected into App and build flows |
| `release.py` | Release entry | Strict native release coordination |

`architecture/` owns architecture scanners, immutable-base classification,
validation planning/reuse, the contract registry and the managed Git-hook
installer. Its `AGENTS.md` defines the machine-governance rules.

The remaining root files are internal implementation, not stable user commands.
They are grouped without compatibility wrappers, with every caller updated in
the same change:

| Internal files | Category |
| --- | --- |
| `internal/bootstrap/report.sh`, `internal/bootstrap/runtime_dependencies.sh` | Bootstrap support |
| `assemble_desktop_resources.py`, `build_devtools_web.py`, `build_godot_dedicated.py`, `build_godot_web.py`, `package_python_core.py` | Build support |
| `release_install_smoke.py`, `release_manifest.py`, `release_pipeline.py`, `release_planning.py` | Release support |
| `chat_with_elfie.py`, `e2e_dashboard_check.py`, `verify_nest_runtime_e2e.py` | Manual diagnostics |
| `__init__.py` | Package marker, not a command |

New internal helpers belong under `scripts/internal/<category>/`; stable root
paths stay thin and explicit instead of accumulating unrelated implementation.

### bootstrap.sh usage

`bootstrap.sh` is the unified dependency orchestrator and supports two tiers:

- `dev`: contributor tier — Python dev + frontend + exported Godot Web Runtime + Electron dev deps
- `build`: source/package-build tier — the release toolchain for the current native target

The Godot editor is not a normal startup dependency. Bootstrap resolves it only
when the exported Web Runtime is missing, reuses any executable from the
major/minor line declared by `godot_project/project.godot`, and downloads the
official build only after an explicit `y` confirmation.

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
