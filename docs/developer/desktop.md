# Desktop

The Electron Desktop is an authenticated Observer and public lifecycle client,
not a Runtime supervisor or a product business layer. Its source is
`app/interfaces/desktop/`; the former top-level `desktop/` directory is not a
current module.

## UI role, authority role and leases

The normal UI role acquires an Electron single-instance lock, asks the public
CLI lifecycle client to attach to a healthy Runtime or start one, then opens the
same-origin Core login page. The Core—not Electron—enforces product-route access
and chooses the normal `/chat` or `/manage` landing after authentication.

If the UI attaches, it receives only the Runtime generation. If it starts a
Runtime, it receives its owner lease; only that lease may be passed back to the
CLI to stop the Runtime on explicit application exit. Closing the observer
window never stops a Runtime it did not create.

Godot authority hosting is selected and owned by the Runtime lifecycle
boundary. `electron_authority` is a separate, sandboxed Electron role that loads
the exported Godot Web authority in a hidden window; it has its own instance
namespace and is not the UI role. The Desktop UI contains no Gateway protocol
implementation or authority credential.

## Observer surface

Desktop renders the same authenticated, capability-scoped semantic Observer
surface as other product clients. It may request a resync or focus an already
authorized room or Elfie, and it can submit the separately authorized
high-level interaction request. It cannot read transforms, camera state or raw
Runtime frames. The first phase is deliberately non-video: no camera stream or
JPEG-frame transport belongs to this module.

## Product camera observation

The same-origin Owner-only `/monitor` route renders the full product observation
surface; the Owner Nest-management dialog reuses that same `ObservationMonitor`
surface rather than creating another camera client. Godot owns its complete,
versioned camera catalog: semantic view `id` and `label` values, `active_id`, a
positive `revision`, and `presentation_paused`. The catalog never exposes camera
coordinates, transforms or room geometry.

The React bridge accepts that catalog only from its current same-origin Godot
iframe and only in the strict versioned message format. It may emit only
`overview`, `select`, `reset`, and `set_local_presentation_paused`; `select`
uses an ID already present in the current catalog. It cannot calculate or send
camera positions or transforms, and it cannot access raw Runtime frames,
authority credentials or simulation controls. Local presentation pause freezes
only the Observer's local input/presentation state; it never pauses the Runtime,
Gateway, Core or backend simulation.

## Artifact contract and source checks

The Desktop component is named `desktop-observer` in the Runtime artifact
manifest. It applies to exactly `darwin-arm64`, `darwin-x64`, `win32-x64` and
`linux-x64`; each of those targets also requires `godot-web`, while only Linux
adds `linux-dedicated`. The contract validates target applicability, mode,
entrypoint and file hashes. It describes required artifact shape and does not
assert that an installer exists.

For source checks, use the module's locked Node toolchain:

```bash
cd app/interfaces/desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 test
```

Compiled Desktop interface output belongs in `build/components/desktop-interface/`.
Do not write generated JavaScript, Runtime artifacts, models or user data back
into `app/interfaces/desktop/`.
