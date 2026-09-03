# scripts directory

> Chinese version: [`README_zh.md`](README_zh.md)

`scripts/` holds repo-level launch, build, quality-check and manual diagnosis
entry points. Both end users and contributors should prefer the stable entry
points at the repository root; do not bypass them to assemble your own runtime
environment.

## Layout and stability contract

The root exposes only five stable operational entry points:

| Stable root path | Responsibility |
| --- | --- |
| `bootstrap.sh` | Prepare source-development and package-build dependencies |
| `elfienest.py` | Dispatch the product CLI behind `./elfienest.sh` |
| `serve.py` | Start the foreground service or managed lifecycle |
| `pre_submit_gate.sh` | Run an explicit local commit, push or full checkpoint |
| `release.py` | Coordinate strict native releases |

`README.md`, `README_zh.md` and `__init__.py` are documentation/package metadata,
not additional commands. Single checks such as `python_baseline.py` and
`godot_host.sh` belong under `quality/checks/`; they are implementation details,
not stable root entry points.

```text
scripts/
├── bootstrap.sh, elfienest.py, serve.py, pre_submit_gate.sh, release.py
├── governance/                 # Defines what changes and dependencies are legal
│   ├── contract_registry.py    # Versioned contract inventory
│   ├── change_policy.py        # Immutable-base change classification
│   ├── boundaries/             # App/system/structure/effective-dependency rules
│   └── persistence/            # Database-change inventory and policy scan
├── quality/                    # Executes checks selected by the quality policy
│   ├── checks/                 # Independent Python, Node, environment and Godot checks
│   ├── validation/             # Check planning, gates, candidate evidence, caches and bundles
│   └── hooks/                  # Repository-managed Git hook installation/runtime
└── internal/                   # Replaceable helpers behind stable entries
    ├── bootstrap/              # Bootstrap reporting and dependency resolution
    ├── build/                  # Intermediate build assembly
    ├── release/                # Release planning, manifests and smoke checks
    └── diagnostics/            # Manual and interactive diagnostics
```

`governance/` is the policy layer: it describes ownership, dependency and
contract boundaries. `quality/` is the execution layer: it runs concrete checks
and composes their evidence. `internal/` does not mean private or security
sensitive; it means repo-owned support code whose path is not a public command
contract. Call stable root entries whenever one exists, and invoke a leaf check
directly only for focused diagnosis or when a documented CI/developer workflow
requires it.

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
bash scripts/quality/checks/node_toolchain.sh
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
./developer.sh build-godot-web --check
./developer.sh build-godot-dedicated --check
uv run --no-sync python scripts/quality/checks/python_baseline.py
```

Before a repository-wide pytest run, probe the host once:

```bash
uv run --no-sync python scripts/quality/checks/environment.py
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
| `internal/diagnostics/chat_with_elfie.py` | Runs a long-lived engine loop and chats with the first persisted Elfie in the terminal; requires an adopted Elfie and a model runtime; cleans up services on manual exit |
| `internal/diagnostics/e2e_dashboard_check.py` | Starts the configured model service with a temp directory and random ports to check the login, adoption and management dashboard flow; requires a configured model |
| `internal/diagnostics/verify_nest_runtime_e2e.py` | Waits for a Godot Runtime and verifies two-Elfie sync, broadcast, semantic motion and cancel terminal states |

These scripts may take time, occupy ports or produce local data; they should
not be executed on import, and must not point at default production data without
explicit intent. Automatable regression should live under `test/e2e/` instead.

`internal/diagnostics/verify_nest_runtime_e2e.py` starts the Python-side protocol v2 gateway; in
another terminal you need to launch `godot_project/main.tscn` against the
WebSocket address and nonce the script prints. The script uses only in-memory
state and never reads or writes the production `ELFIE_HOME`.

## Artifact boundaries

- All reproducible intermediate artifacts go into the root `build/`;
- Final installers go into the root `dist/`;
- Production data goes into `ELFIE_HOME`;
- Never write generated Godot Web, Desktop JavaScript, Python Core, logs or
  caches back into `scripts/` or any other source directory.

When adding a script, place policy in `governance/`, executable verification in
`quality/`, and support implementation in `internal/`. Adding another stable
root entry changes the script-layout contract and requires the corresponding
governance review, tests and Developer documentation.
