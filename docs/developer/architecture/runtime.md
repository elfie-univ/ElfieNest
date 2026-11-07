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
`<selected-data-home>/runtime/runtime.json`.

The authority host is selected by `infrastructure/godot/lifecycle/` without
Nest state, scene data or protocol credentials. Exported artifact metadata and
validation live in `infrastructure/godot/artifacts/`:

| Host kind | Display mode | Purpose |
| --- | --- | --- |
| `web_authority` | graphical | Exported Godot Web authority |
| `electron_authority` | graphical | Infrastructure authority selected by the Bootstrap-owned Electron host |
| `linux_dedicated` | displayless | Linux x64 exported dedicated authority |

`godot_project/` remains the editable source project. The Supervisor hosts an
exported Runtime artifact; neither Python nor the Desktop UI reads Godot source
assets as a Runtime dependency.

`app/bootstrap/desktop_host/` is the Electron composition and packaging root.
It dispatches the visible Desktop interface or the Infrastructure authority;
`app/interfaces/desktop/` never imports or packages authority implementation.

## Owner leases and Desktop attachment

After complete health, the Supervisor records an owner lease containing an
`owner_id` and Runtime generation. A client that finds a healthy Runtime
attaches to it and receives the generation but no stop right. A client that
started the generation receives the lease and may stop only that same lease.
This prevents one Desktop window from stopping a Runtime it merely observes.

Startup is still one lifecycle transaction, but it exposes a transient
`startup_owner_id` receipt while the transaction is in progress. The receipt
prevents a second client from starting the same Runtime and lets the owning
Desktop cancel a start through the public `stop --owner-id` command. The
receipt is promoted to the normal owner lease only after the complete Core,
Gateway and Godot readiness contract passes; `ready` is never reported early.

The Electron observer lives in `app/interfaces/desktop/`, not the removed
top-level `desktop/` directory. Its public lifecycle client invokes the
user-visible CLI commands and never imports Supervisor internals, Godot Gateway
protocol frames or authority credentials. It creates a local startup shell
immediately, loads the real management page once Core and Gateway are ready,
and keeps monitor controls disabled until the Godot Observer is ready. Closing
an observer window has no lifecycle effect. An explicit application exit hides
the UI first, cancels an in-flight start when necessary, and then asks the
lifecycle owner to stop the Runtime only when the client holds the owner lease.
The owner gives the hidden authority and managed Core a short graceful window,
then force-stops only the re-validated process group so shutdown cannot hang on
an unresponsive child.

## Observer permissions, camera catalog and the non-video first phase

An Observer starts from an authenticated product session and receives an opaque,
session-bound capability. Its subscription is restricted to either one room or
one owned Elfie, and its interest can only reduce that authorized result. Frames
carry semantic identity and state in a generation/sequence order; they do not
carry scene transforms, geometry, camera state, raw Runtime protocol frames or
authority credentials.

For the product Observer, Godot owns the complete, versioned camera catalog.
Each strict catalog envelope carries semantic view `id` and `label` values,
`active_id`, a positive `revision` and `presentation_paused`. It describes the
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

The product Observer may also receive a strict semantic entity snapshot for
view-only presentation. Each entity carries identity, species, appearance,
room/zone state, a semantic `home_anchor_id` and nullable `action_anchor_id`; it never carries coordinates,
transforms, navigation or collision facts. Godot resolves that anchor locally
and owns actor placement and rendering. The action anchor, posture and active
command are projected from authority snapshots at action start and completion.
Observer replays walking and authored bed/seat poses against its own identical
scene; duplicate or stale snapshots do not restart actions. Local pause stops
display physics only. Product-local random wandering and synthetic waypoint snapshots have been removed.
Unknown action anchors do not fall back to a fabricated home state. Nest Lab retains
its isolated Python scheduler, which sends real semantic movement commands.
The React bridge accepts and forwards only
same-origin, validated snapshots to the current Observer iframe.

Fixed-camera monitoring opens at the garden overview and uses only left-drag look-in-place, right-drag horizontal track movement and wheel zoom, without an operation-mode selector. Movement stays inside the preset floor/region. Reset beside the fixed-view selector restores the current camera’s default position, orientation and zoom without selecting another subject. Elfie views retain follow and first-person perspectives and do not show Reset. Camera and playback controls do not change authority state.

`/monitor` is a signed-in observation page. The Owner/Admin Nest-management
dialog embeds the same `ObservationMonitor` surface and bridge rather than a
separate camera implementation.

The monitor toolbar keeps view controls on the left and pause/resume on the right,
without a vertical divider. Normal `/monitor` follows the live environment and hides
time preview. Opening `/monitor?debug=1` exposes local lighting previews; every page
load starts at live time, with no saved preview. The parameter grants no additional
permissions and previews do not change Nest time or resident behavior. On mobile,
the toolbar sits below the scene, view controls scroll horizontally, pause/resume
stays visible on the right, and debug time preview occupies a second row.
Fixed views are grouped into Courtyard (2), Main Building (4) and Bedrooms (16).
Bedroom options and the selected view carry a small marker matching the building's
exterior color; room and floor labels and the standard selection background stay unchanged.
Monitoring starts
with the garden overview selected initially. The first control is a two-button group,
Fixed cameras / Elfie views, with the active mode highlighted. Fixed mode then shows
the camera selector and Reset; Elfie mode shows the resident and perspective selectors.
Overview is a camera preset without a separate button. Switching to a preset restores its default pose.
The Elfie selector uses the owned directory for ordinary users and the protected
administrator directory for Admin/Owner accounts, with follow and first-person
choices; residents absent from the scene cannot be selected. The backend Observer
filters ordinary users to owned residents for both room and Elfie scopes; managers
can observe all residents. The product Observer
registers both cameras per resident. Only an explicit Elfie-scoped snapshot initially
focuses that resident; room monitoring never selects an arbitrary resident. These
cameras change only the display view, not resident movement or authority state. Follow motion and obstacle-distance changes are smoothed;
other residents do not trigger camera occlusion zoom. A blocked follow camera
prefers a stable clear side around the resident instead of shrinking into its body;
the clearance distance also accounts for the resident's collision height. Completed semantic actions
are replayed by walking to the local anchor before presenting the final pose,
not by teleporting the display actor to the destination.

The closed local navigation intents are `request_resync`, `focus_room` and
`focus_elfie`. The only world-changing request is the separately authorized,
rate-limited high-level `request_interaction` (`greet` or `rest`), which goes to
the world sink through the application boundary. The first Observer phase is
not a camera/video transport: it does not send JPEG frames or provide a camera
stream API.

The Monitor defaults to an automatic cycle: the complete 80-second fixed show, a four-second transition, a 384-second seeded random round, and a four-second return transition. The cycle repeats every 472 seconds. The random choreography contains Six central gestures
(breathing, building, accents, flower opening, alternating petals and travelling
petals) accompany sixteen outer actions: breathing, alternating and opposite
pairs, double waves, cumulative rise/fall, retained height stairs, rotating stairs,
overlapping/paired/growing inward chases, dome opening, and four mixed-direction
patterns. Eight ensemble families coordinate the centre and perimeter rather than
choosing their gestures independently. Each 24-second phrase returns to a live
neutral pose; groups reduce pressure separately while changing direction. Seeded
sixteen-action rounds avoid immediate repetition and vary direction, peak height,
speed and four coordinated palettes. Outer jets are capped at 4 m and the centre
at 6 m. Each petal and outer nozzle sends its own height, direction and landing to
the existing spray/ripple pipeline; the 2304-particle ceiling remains unchanged.
The same seed and elapsed presentation time replay identically, including after
offscreen skips.
The Monitor URL accepts `fountain=fixed` to select the preserved show, or
`fountain=random&fountain_seed=42` for a repeatable random sequence; `fountain=auto` selects the automatic cycle. These are
presentation-only settings, with no changes to authoritative world state.

The retained fixed fountain follows a silent 80-second presentation score at nine fixed
nozzle positions. From 0–28 seconds, the central eight-petal flower grows from
3.3 to 4.6 m, accompanied by low, then alternating vertical outer jets. From
28–40 seconds, pressure drops during the change of direction: the centre becomes
a main plume and the outer eight jets arch inward, landing 0.75 m from the centre.
The main plume reaches 6 m during 40–50 seconds. During 50–66 seconds the outer
jets return upright while the central flower opens to its separate 6 m peak;
66–80 seconds relaxes smoothly back to the opening. The outer nozzle ring remains
about 4 m from the centre, with the spillway between adjacent nozzles.
Vertical water has a tapering white core and a wider falling spray envelope near
the water, without an enlarged crown. A shared GPU batch of at most 2,304 small
water fragments provides spray and impact splashes. Seventeen possible landing
regions (main, outer eight, flower eight) share positions and pressure between
spray and water-surface foam/ripples; inactive landings disappear. Night colours
follow the active shapes, with a warm main plume and cool arches/flower accents.
Moving waves reach the inner wall and continue as two fading spillway arcs,
without increasing coping brightness or adding shadow-casting lights. A 250 ms camera/frustum and
line-of-sight check suspends animation updates and the local light off screen or
behind solid geometry; distant views omit the droplets. Returning to view samples
the elapsed score directly. Monitor pause and page-background suspension freeze
presentation without changing the authoritative world.

## Complete-estate physics and furniture actions

`godot_project/nest/nest.tscn` remains the single world entry. The complete
estate's authored module, floor and furniture metadata bind its physical
colliders and stable interaction anchors; the retired procedural-room coordinates
are not reused. Mirrored render nodes are converted into positive-handed physics
frames without moving the visible geometry. The garden's authored collision
proxies are reused rather than baking the foliage into navigation.

World readiness requires synchronized navigation regions and valid paths from
advertised anchors to the courtyard, not merely a nonempty navigation resource.
The estate exposes a fixed 32-bed semantic catalogue without duplicating the estate.

The native Body exposes `furniture.use` with only `anchor_id` as an argument.
It lowers through the existing authenticated `execute_intent` command to
`use_anchor`; callers cannot supply coordinates or a pose. The same command
physically navigates to the object's approach marker before entering its authored
sleeping or sitting pose. It retains the original intent/body-generation identity
and exactly one terminal result. A plain `move_to_anchor` never uses furniture.
Occupied furniture, unavailable paths, invalid contact metadata and blocked exit
positions fail explicitly. Walking away restores the standing body and collisions.
These operations remain Godot-owned; they do not add a Python geometry model,
a second Gateway, or an Observer simulation authority.

For animation inspection, `use_anchor` additionally accepts an optional named
`furniture_cycle`: `seat`, `sleep-back`, `sleep-left` or `sleep-right`. It selects a
Godot-owned authored sequence rather than accepting a transform or arbitrary pose.
Normal Body `furniture.use` calls still pass only `anchor_id`. The sequence runner,
root motion, contact sampling, chair swivel, sleep poses and duvet deformation live
under `runtime/actor/`; estate contacts and collision shapes remain under `nest/estate/`.
Nest Lab selects and observes the same implementation. Completion, cancellation and
failure use the original command identity and one terminal event.

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
| User configuration, databases, Elfie profiles, local keys and Runtime receipt | Selected product data root | No |
| Reproducible intermediate artifacts | `build/` | No |
| Final release artifacts | `dist/` | No |
| Public documentation source | `docs/` | Yes |

## Production directory contract

The normative target is the
[service-lifecycle contract](../contracts/service-lifecycle): installed App,
tray and global CLI resolve exactly `${ELFIE_HOME:-~/.elfienest}`, with no
remembered third root. Source CLI ignores caller `ELFIE_HOME`; only `start`,
`serve`, `restart` and `stop` accept `--data-home`, while other commands use
session context, an eligible `<current-worktree>/.elfienest.local`, or validated
candidate selection. All lifecycle receipts and product data follow the one
resolved root.

There is no persisted remembered root or `data-home` command. The source shell
keeps its target only in memory for the lifetime of that shell; one-shot source
commands use the default or a revalidated candidate. `uninstall` is exposed
only by the installed CLI.

A single computer has one production Nest root:
`${ELFIE_HOME:-~/.elfienest}`. `nest.db` contains exactly the eight final
Nest-level tables for users, sessions, installation/setup, Nest settings,
Elfies, external bodies, body audit events and embodiment leases. Chat and
memory never use the root database.

Each Elfie uses an immutable `elfie_id` as its workspace name. Display names may
change, but the directory must never move:

```text
${ELFIE_HOME:-~/.elfienest}/
├── nest.db                         # final eight Nest-level tables
├── configs/                        # runtime/auth/food configuration
├── reports/                        # model evidence and validation reports
├── assets/users/<user_id>/         # avatar and isolated local files
├── runtime/                        # runtime.json and locks
├── logs/                           # runtime events and token usage
└── elfies/
    └── <8-digit-elfie_id>/          # stable ID, never a mutable name
        ├── profile/profile.yaml
        ├── assets/ godot/ skills/
        ├── conversations/history.sqlite # final seven chat tables
        └── memory/knowledge.sqlite      # final nine knowledge tables
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

There is one end-user installation path: obtain the matching platform-native
package and install it through the operating system. A release download is a
delivery channel for that package, not a separate installation method.

## Development boundary

Developer Tools defaults to an independent root
`${ELFIE_DEV_HOME:-~/.elfienest-dev}`; the `elfie_lab/`, `nest_lab/` and
`elfie_lab/` and `nest_lab/` underneath must never fall back to reading the production root.
Tests should set both a temporary `ELFIE_HOME` and `ELFIE_DEV_HOME`.

Old roots and schemas are rejected before the application writes anything.
Back up and rebuild the selected data root; there is no compatibility read,
copy, replay, dual write or automatic migration path. New chat lives only
inside the corresponding Elfie workspace.

## Internal contracts

Pydantic models are the single source of truth for internal data structures.
When the code needs one, it can call `model_json_schema()` at runtime; the repo
does not maintain a second JSON Schema file.
