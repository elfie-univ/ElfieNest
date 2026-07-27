# Runtime & data

## One Runtime service and its authority

`app/orchestration/lifecycle/RuntimeSupervisor` is the only lifecycle owner for
one ElfieNest Runtime generation. Source and installed CLI lifecycle commands
use that same boundary. It starts and stops the Python Core and its Gateway,
then starts the selected exported Godot authority host; it does not open the
Godot editor.

A Runtime is ready only when the Core, Gateway and Godot authority are ready.
The configured public Ollama endpoint is probed as a fourth component: its
absence makes the Runtime `degraded`, not an excuse to replace the authority
or to create a private model sidecar. `status --json` reports the closed
component set (`core`, `gateway`, `godot_authority`, `ollama`) and the lifecycle
state. The Supervisor writes the current receipt to
`${ELFIE_HOME:-~/.elfienest}/runtime.json`.

The authority host is selected by `godot_runtime/` without Nest state, scene
data or protocol credentials:

| Host kind | Display mode | Purpose |
| --- | --- | --- |
| `web_authority` | graphical | Exported Godot Web authority |
| `electron_authority` | graphical | A separate Electron authority role for the exported Web authority |
| `linux_dedicated` | displayless | Linux x64 exported dedicated authority |

`godot_project/` remains the editable source project. The Supervisor hosts an
exported Runtime artifact; neither Python nor the Desktop UI reads Godot source
assets as a Runtime dependency.

## Owner leases and Desktop attachment

After complete health, the Supervisor records an owner lease containing an
`owner_id` and Runtime generation. A client that finds a healthy Runtime
attaches to it and receives the generation but no stop right. A client that
started the generation receives the lease and may stop only that same lease.
This prevents one Desktop window from stopping a Runtime it merely observes.

The Electron observer lives in `app/interfaces/desktop/`, not the removed
top-level `desktop/` directory. Its public lifecycle client invokes the
user-visible CLI commands and never imports Supervisor internals, Godot Gateway
protocol frames or authority credentials. Closing an observer window has no
lifecycle effect; an explicit application exit stops the Runtime only when the
client holds the owner lease.

## Observer permissions and the non-video first phase

An Observer starts from an authenticated product session and receives an opaque,
session-bound capability. Its subscription is restricted to either one room or
one owned Elfie, and its interest can only reduce that authorized result. Frames
carry semantic identity and state in a generation/sequence order; they do not
carry scene transforms, geometry, camera state, raw Runtime protocol frames or
authority credentials.

The closed local navigation intents are `request_resync`, `focus_room` and
`focus_elfie`. The only world-changing request is the separately authorized,
rate-limited high-level `request_interaction` (`greet` or `rest`), which goes to
the world sink through the application boundary. The first Observer phase is
not a camera/video transport: it does not send JPEG frames or provide a camera
stream API.

## Runtime artifact contract

The artifact manifest accepts exactly four native targets:
`darwin-arm64`, `darwin-x64`, `win32-x64` and `linux-x64`. Every target has a
`godot-web` Observer component and a `desktop-observer` component; only
`linux-x64` additionally has the displayless `linux-dedicated` authority
component. The manifest validates component mode, entry point, file hashes and
target applicability. This is a contract for artifacts, not evidence that any
particular installer has been built or installed.

## Data directories

| Type | Location | Committed? |
| --- | --- | --- |
| User configuration, databases, Elfie profiles, local keys and Runtime receipt | `${ELFIE_HOME:-~/.elfienest}` | No |
| Reproducible intermediate artifacts | `build/` | No |
| Final release artifacts | `dist/` | No |
| Public documentation source | `docs/` | Yes |

## Production directory contract

A single computer has one production Nest root:
`${ELFIE_HOME:-~/.elfienest}`. The root holds Nest-level facts: `config.yaml`,
`.env`, `foods.yaml`, `nest.db`, backups, Runtime state and logs. `nest.db`
only stores accounts, permissions, Elfie registration/ownership, the Nest world
and Runtime state; it does not accept new chat messages.

Each Elfie uses an immutable `elfie_id` as its workspace name. Display names may
change, but the directory must never move:

```text
${ELFIE_HOME:-~/.elfienest}/
├── nest.db                         # Nest, accounts, ownership and world state
├── config.yaml / .env / foods.yaml # local production config and key references
├── runtime.json                    # Supervisor health, generation and owner lease
└── elfies/
    └── <elfie_id>/                 # stable ID, never a mutable name
        ├── profile.yaml and other profile, memory and work content
        └── conversations/
            └── history.sqlite      # all local-channel chat for this Elfie
```

`history.sqlite` records sessions, channels, senders, user relationships, text,
metadata and attachment references. It does not build user-view local chat
copies or put attachment binaries in the database. Channels such as web,
desktop, WeChat or Feishu all write into this one workspace under the owning
Elfie.

## Development and installation paths

There is one source-development path: work in a checkout and run
`./elfienest.sh`; it checks the locked development environment before entering
the product menu. It is not an installation method.

There are exactly three recognized installation methods: source installation
with `./install.sh` for the current native target; a manually obtained native
installer for the matching platform; and a verified remote bootstrap when its
public endpoint is published. The third method has no public download command
yet. These methods converge on the same artifact contract; this page makes no
claim that an artifact is currently available.

## Development boundary

Developer Tools defaults to an independent root
`${ELFIE_DEV_HOME:-~/.elfienest-dev}`; the `elfie_lab/`, `nest_lab/` and
`runtime_lab/` underneath must never fall back to reading the production root.
Tests should set both a temporary `ELFIE_HOME` and `ELFIE_DEV_HOME`.

`nest.db.chat_messages` is a deprecated table left over from the unreleased
phase. A database upgrade deletes it outright; no compatibility read, copy or
migration path is provided. New chat lives only inside the corresponding Elfie
workspace.

## Internal contracts

Pydantic models are the single source of truth for internal data structures.
When the code needs one, it can call `model_json_schema()` at runtime; the repo
does not maintain a second JSON Schema file.
