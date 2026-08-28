# Commands & dev tools

This page records the stable CLI, build commands and isolated debugging entry
points provided by the current code. Command behavior is defined by
`./elfienest.sh --help`, `scripts/elfienest.py` and the corresponding tests.

## Prepare the locked environment

ElfieNest is pinned to CPython 3.9.25, with dependencies pinned by `uv.lock`:

```bash
./elfienest.sh
./elfienest.sh version
```

Contributors also need the dev dependencies:

```bash
uv sync --locked --extra dev
```

Source development uses the in-repo `./elfienest.sh`. End users install a
platform-native application package instead of running commands from a checkout.
Native installers also expose the packaged management CLI as the global
`elfienest` command; it reuses the installed Desktop Controller and production
data root without opening the Viewer.

The two CLI surfaces are intentional: the source-development `./elfienest.sh`
does not register the `desktop` command, while the installed management CLI
does because it can activate the packaged Desktop Controller. `serve` remains
the source-development foreground entry point.

Python `3.9.25` is the common pinned runtime for both the product and the
development tools. Unless the maintainer explicitly approves a full-repo
upgrade, you must not switch to system `python` / `python3`, another virtual
environment, or an `ELFIENEST_PYTHON` override entry; source CLI, Developer
Tools, tests and code review all go through `uv` and the repo's `.venv`. When
the environment is unhealthy, run `./elfienest.sh version` to repair the dev
dependencies.

### Node.js and pnpm toolchain

The private root `package.json` anchors Node.js 20+ and pnpm 10.12.1 without
owning application dependencies. The Web frontend, desktop host, docs site and
Developer Tools retain independent manifests and lockfiles. Check that their
toolchain declarations remain aligned with:

```bash
bash scripts/quality/checks/node_toolchain.sh
```

## Preview the documentation site

Run the VitePress development server and open the local site in the browser:

```bash
./developer.sh docs
```

The server watches `docs/` and reloads the page as Markdown or site configuration
changes. Stop it with `Ctrl-C`. Pass VitePress options after the command when
needed, for example `./developer.sh docs --port 4317`.

## CLI entry points

Running `./elfienest.sh` directly enters interactive mode; scripted calls
should pass an explicit subcommand:

| Command | Current use |
| --- | --- |
| `serve` | Run the service in the foreground (dev/diagnostic mode) and show logs |
| `start` | Start the service in the background; do not start again if already running |
| `status` | Show registered services and port status |
| `stop` | Stop the services registered by the current project |
| `restart` | Stop and restart the current service |
| `web` | Open the web management console for an already running service |
| `mobile` | Show the current Wi-Fi and mobile QR-code access information |
| `config` | Open the arrow-key configuration center |
| `doctor` | Check the local environment and configuration |
| `owner` | Open the Owner account menu in the local terminal |
| `db` | Show database info, or run `backup` / `reset` |
| `version` | Show the version |
| `build-godot-web` | Build, incrementally ensure, or check the browser 3D Runtime |
| `build-godot-dedicated` | Build or check the displayless Linux x64 authority Runtime |
| `developer` | Enter the isolated Developer Tools |

Foreground and background services support code-validated parameters:

```bash
./elfienest.sh serve
./elfienest.sh serve --port 8001 --godot-ws-port 8768
./elfienest.sh start
```

The installed global CLI intentionally does not expose `serve`; its `start`, `restart`
and `stop` commands operate the one installed Controller and its fixed product data root.
It does not accept the source CLI's `--data-home`, `--port` or `--godot-ws-port` options.

After a successful background `start`, the CLI prints the loopback Web console
URL. `web` only opens that already-running Web console; `mobile` prints the
current Wi-Fi network as Step 1 and a QR code for the LAN URL as Step 2.

The service uses the configured model food and provider. Setup keeps public Ollama
optional and binds exactly one chosen endpoint; a model provider must be configured
before chat or adoption can be verified.
The source lifecycle parameter surface is intentionally small: `serve`, `start` and
`restart` accept `--data-home`, `--port` and `--godot-ws-port`; `stop` accepts only
`--data-home`. The installed CLI uses the Controller's automatic endpoint allocation
instead of these source-only options.

In source development, `serve`, a `start` that finds the service stopped, and an
explicit `restart` check the frontend source fingerprint at that launch moment
and rebuild the Web client with the pinned pnpm version when it is stale. A
`start` that finds a verified running service and `stop` do not watch or rebuild
the frontend while the service is running. Installed release mode is unchanged.

## Data and high-risk commands

Installed entrypoints use exactly `${ELFIE_HOME:-~/.elfienest}`. The source CLI
ignores caller `ELFIE_HOME` while selecting a task and accepts `--data-home` only
for `start`, `serve`, `restart` and `stop`. Other source commands use the
in-memory interactive-session target, an eligible
`<current-worktree>/.elfienest.local`, or a revalidated candidate selection.
There is no persisted active-data-home command. Tests, doc verification and
experiments must still set an isolated environment/data root to avoid
day-to-day data.

Owner recovery is offered only in the local terminal; the password is entered
via hidden input and must never go into command arguments, environment
variables or shell history. Service keys are read from environment variables or
Git-ignored local configuration; example docs may only use placeholders.

```bash
./elfienest.sh owner
./elfienest.sh db
./elfienest.sh db backup
```

`db reset` resets the local database; before running it you must confirm the
exact data directory `ELFIE_HOME` points at and keep a backup. The CLI does not
provide a legacy-data migration entry; new configuration and chat use only the
current directory contract.

## Godot Web build

The Godot source project's sole compatibility-version declaration is the first
entry in `godot_project/project.godot` `config/features`. The build machine must
use that same major/minor line and matching Web Export Templates:

```bash
GODOT_BIN=/path/to/godot ./developer.sh build-godot-web
./developer.sh build-godot-web --ensure
./developer.sh build-godot-web --check
GODOT_BIN=/path/to/godot ./developer.sh build-godot-dedicated
./developer.sh build-godot-dedicated --check
```

The official output lives at `build/components/godot-web/` and is not committed
to Git. For the specific environment, artifacts and packaging flow see
`godot_project/WEB_EXPORT.md` inside the standalone Godot source project.
The dedicated authority export is a Linux x64 executable at
`build/components/godot-linux-dedicated/ElfieNestRuntime`; it has no Web
payload and is also not committed to Git.

`./elfienest.sh serve` and `./developer.sh` in the source tree default to the
development lifecycle: before starting they compare the Godot source tree
fingerprint and auto-run `--ensure` when missing or stale; they do not
re-export when nothing has changed. `ELFIENEST_RUNTIME_MODE=release` only runs
`--check` and refuses to start when a validated runtime is missing. The export
machine must have the declared Godot compatibility line and matching Web Export
Templates installed; if they are missing, the service clearly reports why the
3D preview is offline, and the chat and management APIs never fake "preview
OK".

## Developer Tools

Development experiments all enter through `./developer.sh` and never start the
end-user product entry:

```bash
./developer.sh --help
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab
./developer.sh brain-eval --data-dir /tmp/elfienest-brain-eval
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab
./developer.sh brain-eval catalog
```

- The three page entry points share HTTP `127.0.0.1:9001` by default;
- Nest Lab's Godot WebSocket is an internal `127.0.0.1:9002` listener;
- `brain-eval` without an action opens the batch evaluation page, while explicit
  actions such as `catalog` remain the artifact CLI and write to `build/brain-eval/`.

Ports are only local defaults, not production guarantees. Configure the model
from Elfie Lab's experiment panel; saving does not validate the connection and
the first real turn makes the model request. For the detailed boundaries see
`devtools/README.md`.
For reproducible Candidate capture, Judge calibration, protected confirmations, and
promotion decisions, see [Brain evaluation workflow](./brain-evaluation).

## Quality checks and tests

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/quality/checks/python_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit \
  uv run --no-sync pre-commit run --all-files
```

Local docs site build:

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

Desktop uses Node.js 20 and a separate lockfile:

```bash
cd app/interfaces/desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
npx --yes pnpm@10.12.1 test
```

`build/` holds only intermediate artifacts and `dist/` only final installers.
Never write generated output back into source directories.
