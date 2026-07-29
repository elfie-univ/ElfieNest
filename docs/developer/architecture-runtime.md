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

## Observer permissions, camera catalog and the non-video first phase

An Observer starts from an authenticated product session and receives an opaque,
session-bound capability. Its subscription is restricted to either one room or
one owned Elfie, and its interest can only reduce that authorized result. Frames
carry semantic identity and state in a generation/sequence order; they do not
carry scene transforms, geometry, camera state, raw Runtime protocol frames or
authority credentials.

For the product Observer, Godot owns the complete, versioned camera catalog.
Each strict catalog envelope carries semantic view `id` and `label` values,
`active_id`, a positive `revision`, and `presentation_paused`. It describes the
currently selectable views without exporting camera coordinates, transforms or
room geometry. React consumes that catalog and may emit only the closed semantic
commands `overview`, `select`, `reset` and `set_local_presentation_paused`.
`select` uses an ID from the current catalog; React neither calculates nor sends
camera positions, transforms or layout facts.

The product bridge accepts a catalog only from the current same-origin Godot
iframe and only in its strict, versioned message format. It exposes no raw
Runtime frames, authority credentials or simulation controls. Local presentation
pause is an Observer input/presentation state only: it must never pause the
Runtime, Gateway, Core or backend simulation.

`/monitor` is an Owner-only full observation page. The Owner Nest-management
dialog embeds the same `ObservationMonitor` surface and bridge rather than a
separate camera implementation.

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
`${ELFIE_HOME:-~/.elfienest}`. The root holds Nest-level facts such as
`nest.db`, backups, Runtime state and logs. Production Runtime configuration is
split by responsibility under `configs/`: `runtime.yaml`, `providers.yaml`,
`tools.yaml` and `food-packages.yaml`. API keys and structured OAuth credentials
live under `configs/credentials/`. `nest.db` only stores accounts, permissions,
Elfie registration/ownership, the Nest world and Runtime state; it does not
accept new chat messages.

Runtime callers still receive one composite configuration object. The storage
boundary merges the three Runtime, Provider and Tool documents when reading and
splits that object again when writing; this is an internal persistence detail
and does not change the Owner API shape. `reports/` is reserved for reproducible
validation output. These directories and their sensitive subdirectories are
created with owner-only permissions. Old root-level `config.yaml`, `foods.yaml`
and `food_history/` are not read or implicitly migrated. Development Runtime
Labs with an explicit `config_home` keep their isolated `config.yaml`, `.env`,
`foods.yaml` and `food_history/` format.

Supported Provider metadata has a separate versioned catalog. The bundled
`ai_runtime/providers/provider-catalog.yaml` is the offline baseline and is
included in wheel and frozen executable builds. A complete, schema-valid
`configs/provider-catalog.yaml` overrides that baseline on the next process
start. Invalid versions, malformed profiles and catalogs containing credential
fields are rejected and the bundled baseline remains active. There is no remote
catalog downloader yet; this override path is the persistence boundary for that
future feature. `configs/providers.yaml` remains user instance configuration and
must not be confused with the metadata catalog.

Provider setup keeps configuration, discovery and verification as separate
facts. Saving a key or endpoint only marks a Provider as configured. Model
discovery records its source, time and result; a failed or empty discovery never
replaces manually entered models. Explicit single or bounded batch checks then
record connectivity status and latency. The current status remains in
`configs/providers.yaml` for fast projection, while every sanitized check is
also written to
`reports/provider-validations/<provider_id>/latest.yaml` and immutable
`history/` entries. Model benchmarks use the same latest-plus-history pattern
under `reports/model-validations/`, with an opaque hashed model directory so a
model ID never becomes a path.

The Owner API exposes an alert-oriented Provider health summary. A passed check
older than 24 hours is `stale`; failed, stale and never-checked configured
Providers require attention. This is a read-time projection, not a background
scheduler. The current phase supports explicit single and bounded batch checks;
periodic scheduling must later be owned by the Runtime lifecycle rather than an
API or Desktop process.

Food packages are versioned YAML configuration, not database-owned model
definitions. Each custom package receives an opaque immutable `food_<hex>` key;
its display name and role assignments may change without changing references.
A package can assign primary, deep-reasoning, vision and verifier models plus
technical model fallbacks. Tool permissions are deliberately absent from the
persisted execution profiles: tools are enabled by Runtime policy and later
bounded by the calling Elfie/request, independently of model selection.

The catalog records one global default package and an optional global fallback
package. The fallback may be remote, but the Owner API returns a warning because
it cannot cover an offline condition. `local_only` is true only when every
configured role uses a Provider declared as local. Built-in semantic recipes
remain available as automatic-generation templates during the transition, but
the persisted catalog and Owner editor accept arbitrary stable package IDs.

Package contents and assignments have different owners. YAML remains the only
source for model roles and parameters. `nest.db.food_package_access` stores
which stable package IDs each user may select, and
`nest.db.elfie_food_preferences` stores at most one primary package ID for each
Elfie. The global default and fallback are always included in the effective
range. An Elfie selection outside that range, or a selection whose YAML package
is missing, projects to the global default while retaining the stored ID for
diagnostics. Deleting a package is rejected while user or Elfie assignments
still reference it.

The application orchestration layer resolves that effective package for each
Elfie at generation time and injects only its stable key into the Brain-to-
Runtime adapter. The Brain does not import the database, Provider catalog or
food models. Runtime keeps task specialization inside the selected package:
complex requests may use its deep role, multimodal requests may use its vision
role, and technical fallbacks remain within that package. If every candidate in
the selected package fails, Runtime makes one attempt with the catalog's global
fallback package. Structured generation downgrades that fallback attempt to
plain JSON text so a local or otherwise less capable fallback is not falsely
treated as supporting native schema mode. Package assignments are resolved for
each generation, so an Owner change takes effect without rebuilding the Elfie.

Each Elfie uses an immutable `elfie_id` as its workspace name. Display names may
change, but the directory must never move:

```text
${ELFIE_HOME:-~/.elfienest}/
├── nest.db                         # Nest, accounts, ownership and world state
├── configs/
│   ├── runtime.yaml                # system settings and Runtime policy
│   ├── providers.yaml              # configured Provider instances and models
│   ├── provider-catalog.yaml        # optional validated full metadata override
│   ├── tools.yaml                  # tool settings, without plaintext keys
│   ├── food-packages.yaml          # active food package catalog
│   ├── food-packages-history/      # food package revisions
│   └── credentials/
│       ├── api-keys.env            # Provider and tool API keys
│       └── oauth/
│           └── <provider_id>.json  # structured refreshable OAuth credentials
├── reports/
│   ├── provider-validations/       # sanitized Provider latest + history
│   ├── model-validations/          # sanitized model benchmark latest + history
│   └── runtime-validations/        # reserved Runtime-wide reports
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
