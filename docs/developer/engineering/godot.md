# Godot

Godot is the single source of truth for houses, geometry, world coordinates,
motion, collision, characters and rendering.

## What belongs in Godot

- Scenes, nodes, rooms and furniture assets;
- Character models, animations, collision and navigation;
- Rendering and spatial interaction of the Web Runtime;
- The adapter layer that exchanges events with the Python Core.

## What does not belong in Godot

- An Elfie's complete identity, memory and personality;
- The Nest's product accounts, adoption and chat rules;
- House blueprints or coordinate facts duplicated on the Python side.

Before opening, running or screenshotting, first check the Godot version in
`project.godot` and any existing processes, then follow the flow in the
[Godot README](https://github.com/elfie-univ/ElfieNest/blob/main/godot_project/README.md)
and [Web export guide](godot.md#web-export).

## Resident lifecycle integration

The authority Gateway uses protocol 4. Environment commands carry `life_phase`
independently of lighting overrides: day/dawn holds every door open; dusk/night
uses the existing proximity and obstruction controls. All residents may enter
all rooms.

Live Nest sessions select Brain embodied input. Hosting requires an authoritative
sleeping pose at the resident's own bed; the virtual body remains under its cover
while the external body is selected. Committed admission identity and time drive
the one-way fourth-floor arrival presentation; reconnecting does not restart its
clock. There is no departure teleport or audio presentation.

Focused scene verification: `bash scripts/quality/checks/godot_host.sh
res://test/test_resident_lifecycle.gd`. Real-device hosting and final visual
acceptance remain separate checks.

## Web export {#web-export}

The product consumes the exported Godot Web Runtime rather than the
`godot_project/` source project. Developers changing Godot resources and CI build
machines need Godot and official Export Templates; end users do not.

### Paths and artifacts

| Content | Path |
| --- | --- |
| Godot source project | `godot_project/` |
| Web export preset | `godot_project/export_presets.cfg` |
| Official Web Runtime | `build/components/godot-web/` |
| Web entry | `build/components/godot-web/elfienest.html` |
| Build manifest | `build/components/godot-web/build-manifest.json` |

The output must include:

```text
elfienest.html
elfienest.js
elfienest.wasm
elfienest.pck
build-manifest.json
```

Ship any additional generated JavaScript files, including AudioWorklet files.

### Engine and templates

The first `config/features` entry in `godot_project/project.godot` is the sole
engine compatibility declaration. Use Godot from that major/minor version line
and matching official Export Templates. Do not publish a build with mismatched
versions; the builder rejects them by default.

In the editor, open `Editor > Manage Export Templates`, download or select the
matching official `export_templates.tpz`, install it, then close the dialog.

### Standard build

Run from the repository root:

```bash
GODOT_BIN=/path/to/godot ./developer.sh build-godot-web
```

Alternatively, select the binary explicitly:

```bash
./developer.sh build-godot-web --godot /path/to/godot
```

The builder checks the project and engine versions, exports the release `Web`
preset to a sibling temporary directory, checks the HTML/JS/WASM/PCK files, and
records each file's SHA-256 in the manifest. On success it atomically replaces the
official output; on failure the previous runnable output remains available.

Check existing artifacts without rebuilding:

```bash
./developer.sh build-godot-web --check
```

### Manual editor export

The command-line build is the team standard. To diagnose export issues in the
editor, open `godot_project/project.godot` with the matching Godot version, choose
`Project > Export`, select the existing `Web` preset, click `Export Project`, and
write the entry to `build/components/godot-web/elfienest.html`.

Manual export does not generate ElfieNest's `build-manifest.json`; run the
standard build again after diagnosis.

### Development and release

Do not re-export when Godot resources have not changed. After changing them:

```text
Edit godot_project/ source resources
  -> run Godot scene tests
  -> ./developer.sh build-godot-web
  -> ./developer.sh build-godot-web --check
  -> ./elfienest.sh start
  -> accept the 3D room in the browser
  -> commit Godot source resources and build scripts; CI rebuilds the Web Runtime
```

Release pipelines use the same build command and assemble
`build/components/godot-web/` into
`build/staging/<platform-arch>/resources/godot-web/`. Windows, Linux and macOS
share these WebAssembly assets; three native Godot exports are unnecessary.
`build/` contains reproducible intermediates and is not committed to Git.

`build/components/godot-web/` is the sole canonical export location. Development
Python Core mounts the Web Runtime from there; release assembly copies the same
artifacts to platform staging for Electron to consume. Do not maintain persistent
copies in Desktop or Web source directories. Runtime authority startup and
shutdown follow the [service lifecycle contract](../contracts/service-lifecycle.md).
