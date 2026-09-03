# Virtual Appearance Generation

**Status:** release baseline accepted. The thirteen production semantic regions are frozen. The
anatomy-spanning body-motif experiment is recorded but deferred and disabled in product candidate
generation; it is not a release dependency.

> Design relations: **Owner:** Elfie / Embodiment; **Parent:** [Elfie top-level module design](./elfie-top-level-module-design.md);
> **Children:** none; **Normative contracts:** [Species asset-package contract](../../contracts/species-asset-package.md);
> **Current architecture:** [Module boundaries](../../architecture/module-boundaries.md); **Conformance:** none;
> **Domain sources:** Elfaria species and appearance inputs by stable source identifier.

## Scope and ownership

This design defines the immutable generated appearance of an Elfie's Godot virtual body. The
result belongs to `Profile / VirtualAppearance`; Godot owns the geometry, skinning, material and
rendering facts. It does not describe the physical toy body.

The current release appearance consists of geometry plus three ordered skin layers. A fourth,
anatomy-spanning body-motif layer remains a separate deferred experiment:

| Part | Purpose | Composition rule |
| --- | --- | --- |
| Geometry | Height, body build, head/face proportions and appendage proportions | Resolved before material rendering |
| Skin 1: base coat | Transfer the original fur response to one full-body target color | Use the frozen V9 relative-tone method on the original 3D material texture |
| Skin 2: regional accents | Recolor up to two approved semantic regions | Use the same local relative-tone transfer, never a flat overlay |
| Skin 3: safe local mark | One forehead glyph, blush, freckles, mole or heart | Optional, at most one, always inside an allow-listed safe zone |
| Deferred: body motif | A continuous motif over rear head, back and limb branches | Disabled until multi-angle continuity reaches the visual bar |

Protected identity details are a hard mask across all skin layers: eyes, nose, mouth, muzzle,
explicit species white-detail zones and other reviewed exclusions cannot be reached by a free
procedural placement.

## Creation inputs and the four appearance questions

Species, exact age and sex are generation inputs, not decoration options. Species strongly selects
the model, proportions, masks and palette weights. Age strongly affects growth and allometry. Sex
is only a weak biological prior for adult proportions and never chooses colors or marks.

| Product question | Target choices | What the answer controls | Current state |
| --- | --- | --- | --- |
| Height | small / standard / tall / any | Growth-aware total height, with correlated arm and leg length | Partly effective through bone/global scale |
| Build | slim / standard / round / any | Chest, waist, belly, hip and limb thickness morphs | Not visually effective until the GLBs provide the required blend shapes |
| Head and face | soft / balanced / defined / any | Head scale, eye proportions, cheek fullness and muzzle proportions | Head bone scaling is available; full face shaping is not implemented |
| Signature | warm / marked / ears / any | Warm-coat preference, one safe local mark, or stronger ear variation | Implemented for the release vocabulary; anatomy-spanning body motifs are excluded |

The product must not present build or full face shaping as effective while their model assets are
missing. Base coat selection remains an identity choice independent of signature density.

### Geometry rules

Height is continuous, not a four-value lookup:

```text
height = species baseline
       + continuous age-growth contribution
       + user stature shift
       + weak adult sex prior
       + bounded individual variation
```

- Final height scale is bounded to `0.82–1.18` around a standard adult of the species.
- Growth variation is strongest during youth and is derived from exact age within the stage; stage
  boundaries cannot create a visible jump.
- `small`, `standard` and `tall` bias the lower, middle and upper parts of the valid age range rather
  than forcing one fixed scale.
- The adult sex prior is weak (about `±2.5%` in height); youth receives a reduced prior. It cannot
  determine palette, regions, glyphs or micro marks.
- Youth uses a relatively larger head and shorter limbs, converging continuously toward adult
  allometry. Appendage variation remains bounded and correlated so hands, paws and tail cannot
  detach visually from the silhouette.

## Active skin layers

### 1. Base coat

The Shader reads the original GLB material texture through UV, applies the frozen V9 relative-tone
transfer and renders the result directly on the animated 3D surface. It preserves source fur
luminance variation, dark identity details and the reviewed light-region behavior. Screenshot
post-processing and a second recoloring implementation are forbidden.

### 2. Thirteen semantic regions

The first thirteen masks and their reviewed positions remain unchanged. At most two color-capable
regions may be recolored. When two are enabled, they share one accent color with `85%` probability;
the remaining `15%` uses a pre-approved compatible pair.

| ID | Region | Allowed operation |
| ---: | --- | --- |
| 0 | head tuft | color |
| 1 | forehead mark zone | alien glyph only |
| 2 | ear pair | color |
| 3 | ear-tip pair | color |
| 4 | cheek fluff | blush, freckles or mole only |
| 5 | chest tuft | color or heart |
| 6 | belly center | heart only |
| 7 | forearm and paw pair | color |
| 8 | rear elbow patch pair | color |
| 9 | lower-leg and foot pair | color |
| 10 | front knee patch pair | color |
| 11 | tail tip | color |
| 12 | tail underside | color |

Color-capable IDs are `0, 2, 3, 5, 7, 8, 9, 10, 11, 12`. The default accent-count distribution is
`40% none / 45% one / 15% two`.

### 3. Safe local mark

The release supports one mark in total. A candidate may receive one forehead glyph or one micro
mark; the two are deliberately mutually exclusive until a two-mark composition has been reviewed.
Forehead glyph families are crescent, S glyph, double spiral, constellation, comet, alien rune,
diamond, star, lightning, wave and halo. Micro marks are:

| Mark | Placement and shape | Palette rule |
| --- | --- | --- |
| Blush | soft bilateral cheek haze; never a hard white disc | soft peach or dusty rose |
| Freckles | three to five tiny cheek dots | warm brown or rose-brown |
| Mole | one tiny unilateral cheek dot | chestnut or smoky charcoal |
| Heart | one small chest or belly symbol | compatible rose or signature color; no emission |

## Validated palette budget

The release uses the ten coat colors already visually reviewed for each species. Dog uses snow
white, ivory, cream, honey gold, apricot, russet, chestnut, chocolate, silver gray and smoky
charcoal. Fox uses ivory, cream, champagne, golden, orange red, fox red, chestnut, sable brown,
silver gray and smoky black. Regional accents and marks select only from each species' configured
allow-list. Expanding into blue, violet, teal or emissive colors requires a separate multi-angle
palette review and is not claimed by this release.

## Stability and five-candidate diversity

All proportions, colors, region choices and local marks are generated once and
persisted with the immutable appearance provenance. Shader randomness is seeded and stable: marks
cannot crawl, flicker or change when the actor animates, moves into the world or is adopted.

Five candidates are selected by visible distance, not five unchecked independent draws. A batch
rejects duplicate visible keys and varies coat color, silhouette, regional accents and safe local
marks within the user's requested mode.

## Deferred anatomy-spanning body motifs

The retained experiment used a pre-authored 1:2 atlas, species-specific rear-body region clipping
and piecewise head/shoulder/hip anchors before baking the result to the original UV. Rear views were
promising, but side views exposed stretched and abruptly clipped strokes on upper arms and thighs.
The root cause is that the atlas was still mapped through a 2D body projection rather than a
continuous limb-local or three-dimensional anatomical path coordinate system.

For this release, no body-motif parameter is generated, resolved or consumed by `ActorAppearance`.
The written experiment result remains as reference material; its duplicate Shader harness and atlas
were removed during production cleanup. Re-enabling the feature requires a new review of a true
anatomical-path/UV-bake implementation across front, three-quarter, side, back and top views for
both dog and fox. It must not alter the frozen V9 transfer or the thirteen production regions.

## Acceptance sequence

1. Verify the frozen V9 transfer, thirteen regions, local marks and geometry through the formal
   `ElfieActor.configure()` render path for dog and fox.
2. Verify exact-age growth and the weak sex prior while retaining bounded individual variation.
3. Verify persistence in the real Godot world and complete the isolated-data adoption flow with a
   real frontend screenshot of five visibly distinct candidates.

Performance optimization remains a separate follow-up and cannot replace these visual acceptance
gates.
