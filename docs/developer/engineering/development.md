# Development flow

This page covers the standard development path from preparing the environment
to finishing local verification. The specific CLI, Godot and Desktop commands
live in [Commands & dev tools](./tooling); the collaboration policy follows the
[Contributing guide](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md).

## Prepare the locked environment

The project is pinned to CPython `3.9.25`, with dependencies pinned by
`uv.lock`:

```bash
./elfienest.sh version
uv sync --locked --extra dev
uv lock --check
```

Do not write your own `pip install` flow, and do not edit the lockfile to work
around a local environment issue.

Unless the maintainer explicitly approves a full-repo upgrade, CPython `3.9.25`
is an immutable contract: do not modify version files, lockfiles, CI or launch
scripts because of the local default interpreter, a single dependency or a
local feature. All agents, developers and automation may only use `uv` and the
repo's `.venv/bin/python3`; do not call system `python` / `python3`, other
virtual environments, or an `ELFIENEST_PYTHON` override. When the environment
is wrong, run `./elfienest.sh version`, then use `uv run --no-sync` only with
the repaired locked environment.

除非负责人明确批准一次全仓升级，CPython `3.9.25` 是不可变契约：不得因为本机
默认解释器、单个依赖或局部功能修改版本文件、锁文件、CI 或启动脚本。所有 Agent、
开发者和自动化只能使用 `uv` 与仓库 `.venv/bin/python3`；不要调用系统
`python`/`python3`、其他虚拟环境或 `ELFIENEST_PYTHON` 覆盖。环境不正确时运行
`./elfienest.sh version`，再使用 `uv run --no-sync` 执行已锁定的命令。

## Pick a test layer

The test directory mirrors the source boundaries. Run the tests closest to your
change first, then widen the verification scope:

```bash
# Example: only changed the cognitive coordinator
uv run --no-sync pytest test/elfie/brain/reasoning/test_coordinator.py

# Required for any cross-module or directory-boundary change
uv run --no-sync pytest test/architecture/

# When you need full regression
uv run --no-sync python scripts/quality/checks/environment.py
uv run --no-sync pytest test/
```

If the preflight returns `2`, do not run `pytest test/` in the blocked
environment and repeat it later. Run the same full command once on a host that
permits loopback binding; see [Testing & quality](./testing) for the exit-code
meaning.

`test/architecture/` guards against legacy top-level packages, illegal reverse
dependencies, root-level test files and engineering-config regressions. For the
full directory and marker reference see the
[test README](https://github.com/elfie-univ/ElfieNest/blob/main/test/README.md).

## Run the quality gate

The repo currently carries a set of historical Ruff and MyPy diagnostics
recorded by hash. The unified quality gate lets the historical set live on but
blocks any new diagnostic:

```bash
uv run --no-sync python scripts/quality/checks/python_baseline.py

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

./developer.sh brain-eval \
  --data-dir /tmp/elfienest-brain-eval --port 9001

./developer.sh nest-lab \
  --data-dir /tmp/elfienest-nest-lab --port 9001 --godot-ws-port 9002
```

- Elfie Lab inspects a single Elfie's profile, perception, decisions and turns;
- Nest Lab starts an isolated Nest, an independent Godot v2 gateway and an
  optional browser room preview; it does not start `ElfieNestEngine` and does
  not read production data;
- Elfie Lab's experiment configuration can select a local Ollama model or save
  an OpenAI-compatible URL, Token and model as one Lab test Food. It does not
  preflight the connection; the first real turn attempts the model call.

The default ports are only local development values. Do not wire the
workbenches into end-user navigation, and do not let them use default
production data. The real App uses `8000` / `8765`; all three Developer Tools
pages use HTTP `9001`, with Nest's Godot WebSocket on internal `9002`.
Launching the same default service safely restarts the old instance in the
current workspace; explicit ports are for parallel experiments and do not
terminate existing instances. For the detailed
boundaries see the
[Devtools README](https://github.com/elfie-univ/ElfieNest/blob/main/devtools/README.md).

## Product Web and LAN mode

The Core serves five same-origin product pages: `/setup` for local first-run,
plus `/login`, `/chat`, `/manage` and `/monitor`. The first Owner can only be
created through the local or Electron loopback service; afterwards, devices on
the same network segment go straight to the login page. The account hierarchy is
strictly `owner > admin > user`: Owner is the single governance account, Admin
is a full management account, and User is a chat-only account. User requests to
`/manage` or `/monitor` server-redirect to `/chat`; Owner and Admin can use both
management pages and may switch their own default page to chat.
After Owner setup, `/login` also offers public registration for ordinary User
accounts. A successful registration creates a User-only account and signs the
browser in immediately; the first Owner flow and later role changes remain
administrator-controlled.

### Web localization contract

The product Web UI supports Simplified Chinese (`zh-CN`) and US English
(`en-US`). Locale initialization uses this order:

1. a valid saved value from local storage key `elfienest.locale`;
2. the first supported match in `navigator.languages` (`zh-*` maps to
   `zh-CN`, and `en-*` maps to `en-US`);
3. Chinese fallback when neither source is supported or available.

An invalid saved value is discarded. Switching language updates the i18n
instance and the document `lang`/`dir` metadata immediately, then persists the
closed locale value when browser storage is available. The preference is a Web
presentation setting: it does not change session, URL, selected entities,
drafts, setup progress or the saved color theme.

All product-owned labels, actions, help text, validation and accessible names
belong in the typed `common`, `auth`, `setup`, `account`, `chat`, `manage` or
`monitor` resources. User content, backend business data, IDs, provider/model
names and raw protocol payloads are not translated. English error surfaces do
not display arbitrary backend `detail`; they use the localized fallback for a
closed operation code. Chinese may retain a non-empty backend detail when it is
the most useful local diagnostic.

The Electron application menu follows the operating-system locale separately
and supports the same Chinese/English closed set, with Chinese fallback. It
does not read `elfienest.locale` and there is no preload, IPC or storage bridge
between the native menu and the Web language switcher.

Localization acceptance covers all five routes (`/setup`, `/login`, `/chat`,
`/manage`, `/monitor`) in both languages at 375, 768 and 1280 CSS pixels. It
also includes 200% zoom at mobile and desktop widths, keyboard-only switching,
long English copy, offline/error states, refresh and deep links, and smoke tests
for `warm-paper`, `harbor-blue`, `orchid-archive` and `moss-green`. A language
change must not introduce horizontal page scrolling, clipping, lost focus or
lost product state.

The chat page uses the same-session authentication as REST over the same-origin
`/api/v1/ws/chat`. User messages get real-time confirmation; Elfie replies
produced by the runtime are written into chat history first and then bridged to
the same-origin chat connection of the owning user, so history and real-time
messages stay consistent after refresh.

`/manage` is the shared Owner/Admin management page. It is grouped into
monitoring, business management, model subscriptions and system configuration,
and covers users, global read-only Elfie filtering, Elfie nest beds/slots,
provider subscription setup and validation, model lists, food policy,
tools/permissions and system settings. Runtime-event summaries are folded into
monitoring, and Godot live preview is entered from the nest camera panel rather
than through a separate Godot configuration page. In the user panel, only a
strictly higher role can add, remove or reset a lower role: Owner may manage
Admin/User, Admin may manage User, and neither role can manage itself or a
higher/equal role. There is one Owner, at most five Admin accounts, and at most
16 accounts in total; User has no separate cap. Profile and Elfie-limit fields
remain read-only in that panel. Chat, adoption and private personal Elfie
profiles belong only to `/chat`; the management page has no user-Elfie
ownership assignment entry.

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
credentials on `/api/v1/ws/bodies`; browser users always use session cookies.

`/api/v1/ws/bodies` does not accept free-form JSON: every text frame is capped
at 64 KiB, declares protocol version `1`, an event ID and UTC occurrence time,
and may only be `heartbeat`, `sensor_event`, `receipt` or `command_poll`.
Sensor events and action receipts directly reuse the type
contracts from `elfie.body.contracts`; the Core queues actions into the next
`command_poll` of a connected device through `DeviceGatewayTransport`. Device
credentials are shown only once, at registration or rotation, and must never be
written into browser logs, test fixtures or the repository.

The current product acceptance focuses on `/setup`, `/login`, `/chat`,
`/manage`, `/monitor`, the Electron login entry and mobile browsers. Owner configuration of
the device–embodiment lease–capability claim, device throttling policy and the
real-installer staging / dual-client automation remain in phase two; the legacy
single-page console has been retired.

## Pre-commit checks

Before delivering a change set, run the focused tests justified by the changed
behavior. The repository-managed commit hook then checks the staged diff,
Gitleaks and staged Python Ruff only. The exact PR candidate uses the
immutable-base manifest, `elfienest/ci-gate` and the native merge queue; the
complete all-lane backstop runs after main or for explicit full/release
validation. Confirm at least:

1. The tests directly corresponding to the change pass;
2. Architecture tests pass when the affected manifest selects that boundary;
3. Changed-file quality and secret checks pass;
4. When docs are changed, VitePress builds cleanly;
5. There are no real keys, local absolute paths, caches or build artifacts;
6. README, architecture docs and tests stay in sync after adding directories or
   cross-boundary dependencies.

```bash
bash scripts/quality/hooks/install.sh
# optional reusable checkpoint or diagnostic replay:
bash scripts/pre_submit_gate.sh --stage commit --base-sha <immutable-base>
bash scripts/pre_submit_gate.sh --stage push --base-sha <immutable-base>
```

The hook has a 20-second warm target and performs no tests, MyPy, pnpm, Godot,
fetch or network work. Ordinary push does not wait for either optional replay.
Successful results may be reused only for their exact declared inputs. Unknown,
governance and toolchain changes select all premerge lanes. Do not merge current
main into the candidate merely because main advanced; only a new candidate SHA
or an actual conflict invalidates its evidence.

```bash
pnpm --dir docs install --frozen-lockfile
pnpm --dir docs build
```

For PR scope, test evidence and review requirements see the
[Contributing guide](https://github.com/elfie-univ/ElfieNest/blob/main/CONTRIBUTING.md)
and the
[PR template](https://github.com/elfie-univ/ElfieNest/blob/main/.github/pull_request_template.md).

## Common issues

### uv or Ruff cache is not writable

Put the cache in a temporary directory; do not delete the repo or user data:

```bash
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
