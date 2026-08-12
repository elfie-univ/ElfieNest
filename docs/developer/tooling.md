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

`./install.sh` does not use `sudo`; a full install creates the user-level
`elfienest` and `uninstall-elfienest` commands. Source development can also
always use the in-repo `./elfienest.sh`.

Python `3.9.25` is the common pinned runtime for both the product and the
development tools. Unless the maintainer explicitly approves a full-repo
upgrade, you must not switch to system `python` / `python3`, another virtual
environment, or an `ELFIENEST_PYTHON` override entry; install, CLI, Developer
Tools, tests and code review all go through `uv` and the repo's `.venv`. When
the environment is unhealthy, run `./elfienest.sh version` to repair the dev
dependencies; use `./install.sh` to install the native application, then
confirm it with `elfienest version`.

### Node.js and pnpm toolchain

The private root `package.json` anchors Node.js 20+ and pnpm 10.12.1 without
owning application dependencies. The Web frontend, desktop host, docs site and
Developer Tools retain independent manifests and lockfiles. Check that their
toolchain declarations remain aligned with:

```bash
bash scripts/check_node_toolchain.sh
```

Python `3.9.25` 是产品和开发工具的共同固定运行时。除非负责人明确批准全仓升级，
不得改用系统 `python`/`python3`、其他虚拟环境或 `ELFIENEST_PYTHON` 覆盖入口；
安装、CLI、Developer Tools、测试和 CR 一律经 `uv` 与仓库 `.venv`。环境失效时只需
运行 `./elfienest.sh version` 让开发入口补齐依赖；需要安装本机原生应用时运行
`./install.sh`，随后使用 `elfienest version` 确认版本。

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
| `web` | Ensure the service is up and open the web management console |
| `config` | Open the arrow-key configuration center |
| `setup` | Run the first-time setup wizard |
| `doctor` | Check the local environment and configuration |
| `owner` | Open the Owner account menu in the local terminal |
| `db` | Show database info, or run `backup` / `reset` |
| `version` | Show the version |
| `build-godot-web` | Build, incrementally ensure, or check the browser 3D Runtime |
| `build-godot-dedicated` | Build or check the displayless Linux x64 authority Runtime |
| `developer` | Enter the isolated Developer Tools |

Foreground and background services support code-validated parameters:

```bash
./elfienest.sh serve --fallback
./elfienest.sh serve --port 8001 --godot-ws-port 8768
./elfienest.sh start --fallback --no-seed-elfie
```

`--fallback` is a development-only simulation mode; it is not a packaged model
provider. Setup keeps public Ollama optional and binds exactly one chosen endpoint.
`serve --force` only tries to stop conflict processes registered by the current
project and confirmed to belong to that service; it is not a generic port
cleanup tool.

In source development, `serve`, a `start` that finds the service stopped, and an
explicit `restart` check the frontend source fingerprint at that launch moment
and rebuild the Web client with the pinned pnpm version when it is stale. A
`start` that finds a verified running service and `stop` do not watch or rebuild
the frontend while the service is running. Installed release mode is unchanged.

## Data and high-risk commands

Installed product data defaults to `~/.elfienest`; source and worktree runs
default to `<current-worktree>/.elfienest.local`. In both modes,
`--data-home PATH` takes precedence over `ELFIE_HOME`, which takes precedence
over the mode default. Tests, doc verification and experiments must set a
temporary `ELFIE_HOME` to avoid polluting day-to-day data.

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

The Godot source project currently declares 4.7. The build machine must use the
same Godot version and Web Export Templates:

```bash
GODOT_BIN=/path/to/godot4.7 ./developer.sh build-godot-web
./developer.sh build-godot-web --ensure
./developer.sh build-godot-web --check
GODOT_BIN=/path/to/godot4.7 ./developer.sh build-godot-dedicated
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
machine must have Godot 4.7 and the matching Web Export Templates installed; if
they are missing, the service clearly reports why the 3D preview is offline,
and the chat and management APIs never fake "preview OK".

## Developer Tools

Development experiments all enter through `./developer.sh` and never start the
end-user product entry:

```bash
./developer.sh --help
./developer.sh elfie-lab --data-dir /tmp/elfienest-elfie-lab
./developer.sh nest-lab --data-dir /tmp/elfienest-nest-lab
./developer.sh runtime-lab --config-dir /tmp/elfienest-runtime-lab show
```

- Elfie Lab listens on `127.0.0.1:8877` by default;
- Nest Lab listens on `127.0.0.1:8890` by default;
- Runtime Lab is a CLI tool with no listening port.

Ports are only local defaults, not production guarantees. `runtime-lab test`
and `runtime-lab chat` make real requests to the model service; confirm the
provider, model, network and cost before running them. For the detailed
boundaries see `devtools/README.md`.

## Quality checks and tests

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_baseline.py
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
