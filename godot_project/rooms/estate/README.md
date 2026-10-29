# Estate source and functional replays

> 中文：[`README_zh.md`](README_zh.md)

`res://rooms/estate/estate.tscn` loads one complete estate through `rooms/nest.tscn`.
Buildings, furniture, base meshes and materials retain the committed baseline.
The integrated GLB adds the approved forest loop, return spur, smooth ground regions,
path-side vegetation changes and nine retained outdoor fixtures (E01–E02, R01–R07).
The scene's `source_sha256` records the original desktop export; `integrated_model_sha256`
and `instance_sidecar_sha256` identify the current integrated inputs.

| Source resource | Current contents |
| --- | --- |
| `ElfieNest-complete-final.glb` | 266,635,048 bytes; selected terrain/fixture additions over the baseline |
| `ElfieNest-complete-final.instances.bin` | 134 landscape groups, 214,750 instances; 13,748,040 bytes |
| `estate_outdoor_lighting.scn` | Authored road/plaza guidance, lake-bank rim, four high poles and 24 forest lamps |
| `estate_spatial.res` | Current-model collision shapes, activity boundaries and native navigation/stair links |

Runtime loads precompiled spatial data and rejects mismatched model, instance or lighting
inputs. Roads, plaza, lawn and the forest path connect; planting, water, facilities and
simplified trunks remain protected. The movement boundary is excluded from perception rays.
Ten physical door leaves (eight authored and two garden) share proximity opening, delayed
closure, reversal and occupied-volume protection. An explicit default-open setter is available;
connecting that policy to the world's day/night phase remains separate from this migration.

Nest supplies local civil time: 06–18 day, 18–24 evening, 00–06 quiet hours. Ordinary lamps and
authored emission follow the same switch; quiet hours retain guidance and occupied-room policy.
Surfaces receive actual lights without the rejected fixed warm term. The product monitor has
independent time/view selectors; preview changes do not alter Nest or residents.

The regular camera catalog contains one courtyard view, four central floors and eight
bedroom/terrace pairs. The monitor adds forest/estate access views and a ring-road view.
Orbit, zoom, limited pan, current-view reset and actor-follow offsets remain available.

After the repository Web build, these explicit local replays use the same project assets:

| URL query | Purpose |
| --- | --- |
| `?observer=product` | Real semantic monitor, live environment and independent time/view controls |
| `?mode=elfie_lab&review=chair` | Swivel-chair sequence and seated forearm clearance |
| `?mode=elfie_lab&review=sofa` / `review=tour` | Sofa approach/mount/sit/leave and connected walking/stair tour |
| `?mode=event_review` | Original duvet sleep, bed-bound embodiment and seven-layer adoption arrival |
| `?mode=animation_journey` | Nine functional previews, with sofa/sleep/water variants; 25 independent source clips plus nod/shake gestures; select to play, pause or replay |
| `?mode=animation_journey&playback=continuous` | Ordered physical journey with stop-at-first-gap reporting |
| `?mode=water_review` | Original fountain jets, outward ring pulses, spillway and natural lake waves |
| `?mode=path_lighting_review&area=estate` | Accepted complete-estate lighting review |

The dropdown opens disposable crops of the real project in one isolated viewport. Selecting
an item destroys the previous fixture and its owned playback clock, including pending waits.
Replay starts that item afresh. Scenario setup places its local sample at the relevant object;
this is explicitly not a continuous route or evidence that skipped travel succeeded.
The main menu combines arrival and platform exit into the confirmed complete rooftop sequence.
Sofa locations, sleep poses and water scenes have secondary selectors; every water scene supports
day/night playback. Individual source clips and head gestures remain separately selectable.
Source clips use the existing species retarget in place. Source assets and confirmed contact
edits remain unchanged. The regular monitor does not enable this mode.

The explicit continuous journey starts with the existing adoption effects, then hands the same actor
to physical movement. Play, pause, chapter inspection, retry at the actual stopped position
and a checklist are local test controls; no resident or world event is created. A new run
restarts the same Web document/engine, with duplicate-click protection and a bounded
world-loading timeout. The first missing integration or blocked route stops the sequence
and leaves all remaining chapters pending. Sleep reuses the original three poses and duvet
controller after the same actor physically reaches the measured bedside. Entry and exit
use the existing furniture contact/visual blend, check foreign obstacles along the sampled
pose path, and retain the existing standing-capsule exit check. The standing collider is
disabled only during the existing furniture contact convention. A played chapter
does not imply visual acceptance, and source-clip auditions do not prove navigation.
The internal-door chapter visits only representative room M01 and returns to the central
lounge; it does not claim coverage of all eight doors. Physical travel retains the confirmed
species-retargeted, in-place idle/walk clips. Collision includes the central stair walls,
glass rails, rooftop solids and solid furniture such as TVs, stools, ottomans and cabinets.
These participate in offline navigation baking; spatial data without the matching explicit
collision policy is rejected, even if a resource inherits a new script default version.
Add `&autoplay=1` to the continuous journey URL to start playback after validated loading;
it does not enable playback in the product observer.

The dropdown's arrival reuses the original event-review actor and seven-layer effects,
night lighting and fixed front camera along the platform steps. Its four phases are
preparation, charge, materialization/landing and walking down. Preparation only lights
the three ceiling rings, broad petal inlays and platform in sequence. Charge uses one
clockwise angular phase for two revolutions of ceiling chases, petals/carrier and the
platform's top blue ring; the outer base and treads stay fixed. Three full-height,
full-width petal volumes converge into an upright column. Each petal face has an ice-cyan
center and matching blue regions on both sides; blue side lighting and the original single
ice-cyan rear line replace moving stripes. Energy rises to the dome, spreads inside-out, and holds
the fully illuminated roof for one second. A separate broad front then travels from
dome to platform before the existing arrival effect reveals the resident.
Continuous opaque inlays on owned ceramic meshes replace
the overlapping transparent petal strips. During landing, effects fade to reveal the
resident; step lighting prelights the walk, followed by the inner and outer floor guides.
The source GLB, collision resources, actor facing and walk-down motion are preserved.
The 28.7-second preview plays once, then leaves the actor visible on the rooftop floor.
Skeletal source clips live in `characters/animation/`; this combined arrival is stored in
`runtime/lab/estate_platform_cycle.gd`, `estate_event_effects.gd`,
`estate_arrival_lighting.gd` and their shaders, with staging in `estate_event_review.gd`.
The owned petal coatings, wide inward columns, core, uplink, dome and moving carrier are
defined in `runtime/lab/estate_petal_charge.gd`; continuous inlays are installed by
`estate_arrival_inlay.gd`. Their shaders and the shared platform timing stay in the same folder.

Replays do not fabricate world events or certify autonomous life. Final integrated appearance,
including the chair refinement, still requires review in the real monitor. No departure effect,
fan beams, regular lake stripes, superseded plaza fixtures or climbing/jump candidate gallery
is part of the selected action chain.

Offline authoring uses the repository's controlled Godot host entry:

```sh
bash scripts/quality/checks/godot_host.sh res://scripts/tools/bake_estate_lighting.gd
# Inspect build/estate-lighting-v4/estate_outdoor_lighting.scn, then publish it here.
bash scripts/quality/checks/godot_host.sh res://scripts/tools/bake_estate_spatial.gd
# Inspect build/estate_spatial/bake-report.json, then publish estate_spatial.res here.
bash scripts/quality/checks/godot_host.sh res://scripts/test/test_estate_precompiled_spatial.gd
```

Intermediates stay under `build/`; final authored resources above are source assets.
Godot import caches remain local and excluded from Git. Web output is produced only by
`./developer.sh build-godot-web` into `build/components/godot-web/`.
