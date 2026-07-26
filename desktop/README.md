# ElfieNest Desktop

> 中文版：[`README_zh.md`](README_zh.md)

`desktop/` is the cross-platform Electron host. It only handles desktop
lifecycle, windows, platform resource discovery and local process supervision.
Accounts, adoption, chat, Nest rules and Elfie cognition do not belong in this
layer.

## Startup & shutdown sequence

`src/main.ts` first acquires the single-instance lock, then resolves dev-time
or installer-bundled runtime resources through
`src/platform/supervisor_config.ts`. The `RuntimeSupervisor` startup sequence is:

1. Start or connect to Ollama and wait for `/api/tags` to be available;
2. Start the Python Core and wait for `/api/health` to be available;
3. Load the Godot Web Runtime inside a hidden `BrowserWindow` with background
   throttling disabled, inject the runtime nonce and camera token generated
   for this launch, and wait for the handshake to complete;
4. Open the same-origin `/login` window; after login, the Core redirects to
   `/chat` or `/manage` based on role.

On shutdown it first closes the hidden Godot Runtime, then stops the Python
Core and the Ollama managed by Desktop. If any component fails to start, all
already-started components are stopped and an error window attributing the
failure to the specific component is shown. When
`ELFIENEST_OLLAMA_EXTERNAL=1` is set, Desktop does not spawn an Ollama process
but still waits for the configured Ollama address to become available.

## Resource discovery

In dev mode you can specify resources through these environment variables
instead of copying local debug binaries into the source tree:

- `ELFIENEST_CORE_BIN`, `ELFIENEST_CORE_CWD`: Python Core binary and working
  directory;
- `ELFIENEST_OLLAMA_BIN`, `ELFIENEST_OLLAMA_URL`: Ollama binary and service
  URL;
- `ELFIENEST_UI_URL`, `ELFIENEST_GODOT_URL`: management UI and Godot web entry
  URLs;
- `ELFIE_HOME`: data directory for this desktop run.

Installer resources are placed per single target under
`build/staging/<platform-arch>/resources/`. The resource manifest supports:

- `darwin-arm64`
- `darwin-x64`
- `win32-x64`
- `linux-x64`

Each target must include the Godot Web `html/js/wasm/pck`, the Vite `web/`
build output of the three product pages, and the platform-matching Python Core
and Ollama executables. Inside the installer, the Python Core is resolved as
`python-core/ElfieNestCore` (`.exe` on Windows) and reads `web/` via
`ELFIENEST_WEB_BUILD_DIR`; both must use the same relative path as in the
resource manifest. `src/resources/resource_manifest.ts` records file sizes and
SHA-256 hashes and rejects any missing resource. For the full staging convention
see [`packaging/runtime-resources.md`](packaging/runtime-resources.md).

Internal-test installers are pinned to `0.1.0`, named
`ElfieNest-0.1.0-internal-*`, with no publish or auto-update configured. The
first macOS and Windows internal builds are neither signed nor notarized;
testers must acknowledge the system origin warning on a controlled device
before installing, launching, running health checks and verifying shutdown.

## Development commands

Requires Node.js 20 and the repo-pinned pnpm 10.12.1:

```bash
cd desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
npx --yes pnpm@10.12.1 test
```

`scripts/assemble_desktop_resources.py` generates `manifest.json` while
assembling staging. At startup Desktop re-validates that manifest before
spawning any managed subprocess; you can rebuild a diagnostic manifest on its
own with:

```bash
cd desktop
ELFIENEST_TARGET=darwin-arm64 \
  npx --yes pnpm@10.12.1 build-resource-manifest
```

`npx --yes pnpm@10.12.1 dev` compiles and launches Electron and may also start
local components; do not use it for static-only checks. `npx --yes pnpm@10.12.1
package` produces the installer, whose output must go only into the root
`dist/`.

## Build boundaries

```text
build/components/desktop/                         TypeScript compilation output
build/staging/<platform-arch>/resources/          single-platform packaged resources
dist/                                             final installers
```

Never write generated JavaScript, the Godot Web Runtime, the Python Core,
Ollama, models or user data back into `desktop/`. When you change the resource
layout or the supervision sequence, update the corresponding TypeScript tests,
this file, and the Developer docs in lockstep.

> Note: `packaging/runtime-resources.md`, `WEB_EXPORT.md`, the Godot character
> specs and `.github/pull_request_template.md` are intentionally not
> dual-language in this round and remain in their original language.
