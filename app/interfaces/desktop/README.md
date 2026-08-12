# ElfieNest Desktop interface

> 中文版：[README_zh.md](README_zh.md)

`app/interfaces/desktop/` is the Electron Observer interface. It owns visible
windows, single-instance UI behavior, platform integration and the public
lifecycle client. It does not own the Runtime, Nest business state, accounts,
chat, Godot Gateway protocol or authority credentials.

## Lifecycle client

The UI role creates a unique owner ID and invokes the public `elfienest`
lifecycle commands. It attaches to an already healthy Runtime, or starts one
and receives the resulting owner lease. The returned generation is enough to
observe; only the matching lease can stop the Runtime during an explicit
application exit. Closing a window intentionally has no lifecycle side effect.

The Core owns login and route selection: Desktop opens the same-origin login
page, then the Core selects `/chat` or `/manage` after authentication.

## Separate authority role

The UI role is not a Godot authority. `app/bootstrap/desktop_host/` is the
Electron composition entry: it dispatches the visible Desktop interface or the
Infrastructure-owned `godot-authority` entry. The authority loads the exported
Godot Web Runtime in a hidden sandboxed window with its own instance namespace.
Desktop source and package metadata do not import or package that authority.

The Observer receives scoped semantic projections and may send only authorized
high-level intents. It never receives scene geometry, transforms, raw Gateway
frames, camera state or authority credentials. The first Observer phase has no
camera/video or JPEG-frame transport.

## Artifact and build boundary

`desktop-observer` is required by the Runtime artifact contract for exactly
`darwin-arm64`, `darwin-x64`, `win32-x64` and `linux-x64`. Every target also
requires `godot-web`; only Linux requires the displayless `linux-dedicated`
authority component. This contract validates artifact metadata and hashes; it
does not claim an installer has been built.

Source checks require Node.js 20 and the repository-pinned pnpm 10.12.1:

```bash
cd app/interfaces/desktop
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
npx --yes pnpm@10.12.1 test
```

Generated interface output belongs in `build/components/desktop-interface/`.
Native package composition belongs to
`app/bootstrap/desktop_host/electron-builder.yml`.
Do not write generated JavaScript, Runtime artifacts, models or user data back
into this source directory.
