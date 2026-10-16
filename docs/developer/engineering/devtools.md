# Developer Tools

## Entry points

The unified entry point is:

```bash
./developer.sh --help
```

The experiment pages share one HTTP service; asset design also has an independent launcher:

| Command | Initial page | Focus |
| --- | --- | --- |
| `./developer.sh elfie-lab` | `/elfie/experiment` | A single Elfie's profile, perception, decisions and turns |
| `./developer.sh brain-eval` | `/elfie/evaluations` | Batch evaluation and reports |
| `./developer.sh nest-lab` | `/nest/experiment` | Fixed rooms, temporary characters, Godot events and semantic motion |
| `./developer.sh asset-design` | `/assets/design` | Independent room and furniture asset preview; HTTP `9001` |

Asset design preserves the approved asset library and complete right-hand 3D control
panel. Its source is `devtools/asset_design/web/`; it reads registered models,
measurements and images from `devtools/asset_design/assets/catalog.json`. New asset versions
reuse this viewer instead of generating HTML pages. It does not start experiment
state or Godot, and does not build their frontends. Open this independent page
with `./developer.sh asset-design`; it is not mounted in the experiment service
or its menus. Layout baselines and read-only boundary tests live in
`test/devtools/asset_design/`. Missing local asset
data leaves an empty workbench. Design assets, catalog and confirmation records belong to
`devtools/asset_design/assets/` and must travel with the tool; `build/` contains disposable output only.

The content menu lists central floors and furniture parts independently; the eight rooftop
terraces share a content choice with an M01–M08 selector. Model, image and comparison modes
retain the selected content and terrace, and returning to the model restores its revision.
Image mode hides the model version picker. Catalog `imageReferences` associate registered
image paths with object IDs: design references apply across revisions, while review images
retain their source revision. Shared terrace concepts do not assign themes to house IDs.

One toolbar switches between 3D, images and reference comparison. All modes share the
same content menu: park overview, building shells, furniture layouts, furniture and
outdoor landscape. Central floors and individual furniture parts have direct choices;
rooftop terraces use the right-hand house selector. The model picker is labelled “版本”
and lists only the selected object's revisions, newest first. Image mode preserves the
object and house selection, hides model version controls, and shows the corresponding
references even when no picture is available. Returning to 3D restores the saved revision.
The title area's right-hand delete button directly removes the current saved version or
picture and selects the next available version in the same group. Version deletion includes
component exports. Exclusive model/image outputs move to `build/asset_design/cleanup/` with the
original catalogue, marks and a hashed file inventory for recovery; shared files and source,
data and support inputs remain available. The deleted ID is removed from cleanup marks.
Deletion does not require a separate marking step or dialog. Historical versions remain
available in the dropdown. Unknown, cross-origin and unsafe-path requests are rejected;
failed writes roll back the catalogue, marks and moved files.
3D requires a registered model. Images and comparison use explicitly associated,
registered pictures; they never infer ownership from a mixed export title.
Whole-estate previews also offer the model's available first, second and third floors
and roof; changing objects keeps a floor when it is still available. Integrated estate
entries precede historical building samples, and group-local latest labels are explicit.
Existing asset bookmarks remain selectable, while an unselected estate opens its first
available integration. Existing image references declared in saved metadata are included when they resolve
unambiguously to registered local images.
The newest usable version is selected within the chosen category and design. Changing
mode preserves a matching saved version where possible and otherwise selects a usable
scheme in that category. Empty modes show an empty state without changing the media mode.
Images are grouped as references, model screenshots,
layouts/dimensions and comparison material; textures remain in asset files.
Comparison uses an explicitly associated reference or a labelled manual choice;
central-floor references never automatically match house terraces. Separate model
files are available through asset files. Object and floor selection live only in
the viewer; available floors come from model tags and houses can be viewed together.
The view controls follow display switches and dimension aids, with a compact `− / Fit / ＋`
row above the existing direction buttons; icon buttons retain accessible labels.
The embedded model and compact sidebar share one grid row and always have the same height.
The viewer reports its actual control and bottom-bar height so controls cannot spill behind
downloads; only the outer page scrolls when the window is too short. Model information,
downloads and expandable interaction help sit in a separate bottom bar.
The media buttons and right-aligned content/version selectors occupy one compact desktop
row. Version descriptions show one line by default; click to expand or hover for the full text.

Object review uses one grouped content selector: estate overview, building shells,
furniture layouts, furniture kits and outdoor environment (only when registered). Floors,
terrace locations and kit parts are selected in the right sidebar, rather than repeated
in the content menu. Original exports appear as historical versions in their content
collection; historical complete scenes remain read-only and all files are retained.
Source-only versions remain selectable for downloading their original files. Supplementary
model files open directly in the shared viewer; file previews do not confirm an object.
Counts and file sizes are measured from unique, existing registered paths when loading the catalog.
Object revisions group identical selected geometry, materials, textures, transforms and
semantic tags across exports. A carried copy does not create another revision; each
revision retains its first observed source and all duplicate source paths. Titles and
revision order belong to the object, not the containing export. Confirmed sources remain
the preview source for their content group. Original files and historical exports remain intact.
Object versions default
to the newest distinct candidate; confirmation adopts exactly that object, even when selecting
an older version. The latest confirmation action determines the adopted version, not its
numeric label. The button names its scope; reference visibility never expands that scope.

Reference furniture/buildings use matching adopted objects and stay pinned for the open
preview. When a building has no confirmation, its newest version is shown as an unconfirmed
reference; viewing or confirming furniture does not adopt that building. Reload to see
subsequent confirmations. The live overview composes adopted
building, placed-layout and environment subsets from their original GLBs, preserving source
transforms. One house shell and one house layout are adopted once and instanced at the
source model’s eight placements. Their position selector changes only the preview.
The eight distinct upper-terrace layouts retain separate M01–M08 scopes. Main-building
layout floors and kit parts also have explicit confirmation scopes; the all-floor and
all-terrace views require selecting a specific scope before confirmation.
Unconfirmed or changed object content is omitted and flagged; unrelated changes in the
same GLB do not invalidate an adopted object. Reference-content changes require a separate
combination check without making the object unconfirmed. The existing confirmation button
offers that check when needed. Standalone samples without estate placement remain historical
versions; confirming a standalone furniture part does not silently replace every instance in
a placed layout. Saved renders are historical images, not live composites.

Adoptions and pinned source hashes are stored atomically in the isolated asset root's
`adoptions.json`; the catalog and asset versions are never rewritten by confirmation.
Object-content hashes identify adoption; whole-file hashes still verify preview downloads.
Content selectors show distinct model-version counts in parentheses, with source-only
records counted separately. Equal historical models share one menu choice; original files,
confirmation records and links remain available. The live overview is not a saved version.
To audit existing exports, run `.venv/bin/python3 -m devtools.asset_design.reindex --report
build/asset_version_audit/objects.json`. After inspection, the same command with `--apply`
checks the original confirmed source hashes, backs up the confirmation file, and adds
object hashes to current confirmations and their references. It preserves historical
confirmation entries and never rewrites or deletes models. Unsupported content is reported
for review and blocks applying the reconciliation.
Conflicting confirmations of the same object require a reload; different objects can be
confirmed independently. Confirmed sources and pinned historical references cannot be
deleted through the cleanup API. Scene plans are temporary and must be reopened after
restarting the workbench. Outdoor models opt in with `design_role: landscape` or
`design_role: environment` scene-node tags (or the corresponding catalog category);
untagged presentation backdrops are not interpreted as garden geometry.
Object, floor, section, display switches, lighting, camera, image and manual reference
selections are saved in the URL. Camera controls do not change the other selections.

They can reuse the underlying libraries and the same Godot Web Runtime, but they
must not depend on end-user auth, `ElfieNestEngine` or production data to start.
When launching an experiment page, the Runtime is auto-checked; it is
re-exported only when missing or when the Godot source has changed.

The Elfie Lab and Nest Lab browser shells share the React + TypeScript + Vite
project in `devtools/web/`. The frontend artifact is generated only into
`build/components/devtools-web/` and never written back to or committed into
source directories; the launch command reuses or rebuilds it based on a frontend
source digest. The Nest Lab camera button only sends a restricted set of
intents — overview, activity area, dormitory, teleport room and reset view —
Godot remains the single source of truth for camera transforms.

Nest Lab embeds the exported fixed room in the browser. Developers can change
the bed count, add a saevi / tovren, start a Python-driven random walk that picks a
semantic anchor on a timer, or pause, resume and reset the experiment. Godot
handles geometry, rendering, pathfinding and collision; the Lab only sends v2
semantic commands and records Runtime facts. Both Labs use the same Godot Web
export as the real desktop run; each just provides an isolated web shell, data
root and local protocol entry.

Local ports are layered by convention: the real App uses `8000` / `8765`, while
Developer Tools exposes one HTTP port at `127.0.0.1:9001`. Running any default
Developer Tool command again safely restarts the current workspace instance; the
Nest page's Godot WebSocket is an internal `9002` listener and is not a second
web page. Only an explicit port keeps parallel instances alive, and an unknown
port occupant is never terminated.

Elfie Lab reads the isolated Runtime `nest.db` food catalog on first launch.
The database seeds the two system rows, which appear as unconfigured until
Ollama or an OpenAI-compatible provider is configured in the page; no synthetic
food row is injected. The configuration form only saves the selected model and
connection. The first real turn is the model connection attempt.

## Asset consolidation

Apply these principles to furniture, rooms and complete buildings:

- Group by independent function, movement and visibility, rather than by colour or
  construction detail. Combine static parts that always operate together; preserve
  separate doors, drawers, controllable lights, building modules and floor visibility.
- Keep bed shells, mattresses, duvets and individual pillows independent. Bindings,
  seams and fixed decorative fittings belong to their owning item.
- Different colours and surface properties can share a mesh through vertex colours
  and PBR texture atlases. Preserve colour, roughness, metalness, normals, emission,
  texture repeat and padding; do not silently flatten every surface to one material.
- Count functional components, mesh objects, material primitives and triangles
  separately. A parent group or a mesh with several materials does not by itself
  reduce draw batches. Transmission or transparency may require separate batches.
- Consolidate groups before any separately approved triangle reduction. Preserve
  positions, dimensions, normals, topology, animation ownership and viewer tags.
- Keep the approved baseline and derive a new local version. Verify geometry,
  material/texture mapping and independent parts, then compare both versions using
  the same camera and lighting in the existing asset-design viewer.
- Record measured counts, appearance changes and texture-memory costs in the asset's
  verification output. Fewer batches alone do not establish faster interaction.

## Data root

The unified interactive service defaults to `${ELFIE_DEV_HOME:-~/.elfienest-dev}` and
write their own configuration, sessions and debug data under `elfie_lab/` and
`nest_lab/`. They never default to `${ELFIE_HOME:-~/.elfienest}`; if you
explicitly pass the production root to Elfie Lab's Runtime configuration, it
is rejected.

Brain Eval creates disposable Runtime state for capture and writes only regenerable
artifacts under `build/brain-eval/<run-id>/`. It rejects production `ELFIE_HOME` and output
paths outside that build tree. Its design and exact batch workflow are documented in
[Elfie Brain evaluation and evolution system](../designs/elfie/brain/elfie-brain-evaluation-system)
and [Brain evaluation workflow](./brain-evaluation).

Local acceptance can isolate both kinds of data at once:

```bash
ELFIE_HOME=/tmp/elfienest-production \
ELFIE_DEV_HOME=/tmp/elfienest-developer \
./developer.sh brain-eval
```

Independent object assets use `devtools/asset_design/assets/<object-directory>/source/model.glb` as their
editable build input. Each published `versions/vNNN/model.glb` contains only that object's geometry,
materials, textures, hierarchy and required placement/measurement helpers. The catalog
owns explicit object/version records; legacy full-scene exports are retained as archived
provenance, not scanned to create new object versions. Floor and terrace overview scenes
compose object references without exporting another combined model.

With the asset service stopped, run `.venv/bin/python3 -m devtools.asset_design.object_assets split`
to extract and verify existing distinct revisions. It checks content hashes before moving
current confirmation pointers to the independent files, preserves confirmation history and
version numbers, and archives earlier revisions of confirmed objects only after verification.
Earlier independent revisions use lossless `.glb.gz` archives; restoration verifies the
file checksum before unpacking. Original files stay in place. Catalog, confirmation and legacy inventory backups plus the
verification report are written to `build/asset_design/backups/object-split-*/`.

Edit one object's `source/model.glb`, then run
`.venv/bin/python3 -m devtools.asset_design.object_assets publish --object building:pod`
(with the service stopped). An unchanged source creates no revision; changed content creates
one revision for that object and requires a separate confirmation. Building and furniture
scopes cannot be mixed. The build reads no legacy export or legacy construction script.
Restore an archived independent revision with
`.venv/bin/python3 -m devtools.asset_design.object_assets restore --object building:pod --revision 31`;
restoration never changes the current confirmation.

## Portable design asset workspace

Design authoring is independent of final Godot delivery. Buildings live in
`assets/buildings/{central,pod}/`; layouts in `assets/layouts/central_floor_N/`,
`pod_bedroom/` and `terraces/M01/`; kits and parts in `assets/furniture/`;
the garden in `assets/landscape/site/`. Each object owns editable `source/model.glb`
and `source/build.json`, immutable `versions/vNNN/model.glb` snapshots, a `version.json`
registration copy, per-version `images/`, and cross-version `references/`.
The root `catalog.json` owns loading and file associations; `adoptions.json` owns
confirmations. File names never imply approval.

With the service stopped, edit the object's source, then publish and register pictures:

```sh
.venv/bin/python3 -m devtools.asset_design.object_assets publish --object layout:central:2 --image build/new-render.png --reference build/new-reference.png
.venv/bin/python3 -m devtools.asset_design.workspace scan
./developer.sh asset-design
```

Publishing deduplicates model content, selects the version directory and registers
image ownership; changed content still requires separate confirmation. `scan` checks
registered files and confirmed content, then writes a derived catalog cache to
`build/asset_design/catalog.json`. A clean machine needs the real versioned assets,
then the same launcher; the old `build/asset_previews/` is unnecessary.
`workspace organize --from-root ... --root ...` explicitly copies into a nonexistent
destination, verifies copies and retains originals. Legacy full-scene exports, logs
and repair history remain local recovery material in build, outside the active
workspace. Copied historical recipes are provenance, not portable generators.
Binary files exceeding the Git host's file limit require Git LFS configuration before
submission and retrieval on another machine; code and pointers without actual binary
content do not prove recovery.
