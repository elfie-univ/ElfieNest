# Appearance Experiment — Phase 2: Patterns, Marks, and Candidate Diversity

**Status:** Feasibility experiments completed for dog and fox; not integrated into production.

**Date:** 2026-08-17

## Why this record exists

Phase 1 established the accepted baseline: recolor the original source fur response with bounded
relative-luminance transfer, preserve dark identity details and light regions, and avoid a broad
overlay that creates gray haze. The product review estimate for that baseline was approximately
8.8/10 for fox and 8.4/10 for dog under the controlled comparison.

This record captures the next experiments so the decisions and limits are findable later. It does
not turn the experimental images into a production shader or alter a GLB, scene geometry,
BlendShape, or face shape.

## Important rejected route

An earlier UV-mask prototype was rendered from front and side views. It was rejected as the
current production direction after visual review: the protected eye/nose regions grew too large,
some fox white-region boundaries remained visibly wrong, and the side-view tail/edge result was
not reliable enough. The mask PNGs and old render script remain as historical evidence only; the
default actor appearance path no longer binds them.

The rejection does not mean texture-space masks are impossible. It means that this particular
hand-authored mask quality was below the product bar and should not be treated as a finished
solution.

## Controlled experiment method

The original dog and fox Godot scenes were rendered with the real Godot OpenGL/Metal renderer at
the fixed 512×512 adoption-card camera. A temporary harness then applied the accepted Phase 1
relative tone transfer and explicit species-specific natural-region masks to the rendered image.
This made the experiments fast and repeatable without starting the service or changing the GLB.

The harness is deliberately a feasibility tool, not a production implementation:

- it proves the parameter combinations and rejection rules can be expressed;
- it preserves the source render’s fur bundles, highlights, and fine detail inside recolored areas;
- its region coordinates are tied to this fixed front camera, so they do not prove multi-angle 3D
  stability;
- production integration still needs semantic/UV region data designed and reviewed per species.

Replay from the repository root:

```text
/Applications/Godot.app/Contents/MacOS/Godot --path godot_project --script godot_project/scripts/test/render_appearance_variation_experiments.gd
```

Use `APPEARANCE_EXPERIMENT_STAGE=baseline|patterns|slots|markings|safe_zones|diversity` to
rerun one plate. The complete script output reports `SAFE_ZONE_REJECTED: dog=1 fox=1` and
`FIVE_CANDIDATE_KEYS: dog=5 fox=5`.

## Results

### 1. Accepted baseline

![Accepted Phase 1 baseline](../../../public/assets/appearance-experiments/phase-2/01-accepted-baseline.png)

The original source render and the silver, cream, and deep-brown/sable transfers remain visibly
fur-like. The result is the reference starting point for every later plate.

### 2. Large natural-region patterns

![Large natural-region patterns](../../../public/assets/appearance-experiments/phase-2/02-large-natural-patterns.png)

The experiment supports different natural-region families per species:

- dog: chest bib, narrow forehead blaze, and paw-sock regions;
- fox: chest, lower face/muzzle, and inner-ear regions.

The source fur detail survives inside the regions, so the mechanism is feasible. The dog forehead
boundary is still only an exploratory fixed-camera mask and is not final art; the final version
needs a region boundary that follows the real fur/UV layout rather than a screen-space shape.

### 3. Color-slot permutations

![Color-slot permutations](../../../public/assets/appearance-experiments/phase-2/03-color-slot-permutations.png)

The same region layout can swap primary and secondary color slots without changing the pattern
geometry. This confirms that a pattern is not merely `pattern_count × color_count`: each pattern
has independently selectable slots, and valid combinations are a product of layout, slot
assignment, palette compatibility, and optional accent choices. Very low-contrast combinations
should be filtered before showing them to a user.

### 4. Local markings

![Local markings](../../../public/assets/appearance-experiments/phase-2/04-local-markings.png)

The prototype covers six mark families—crescent, angular glyph, cross, star/dot cluster, short
dash, and a simple alien-like glyph—at forehead, cheek, and chest placements. The mark layer can
be deterministic and can be combined with a color/pattern key. These are control proofs only:
the black glyphs need a later art pass for scale, edge softness, fur-aligned blending, and
species-specific styling.

### 5. Safe-zone validation

![Safe-zone validation](../../../public/assets/appearance-experiments/phase-2/05-safe-zone-validation.png)

Legal forehead, cheek, and chest placements render. An eye/nose placement request is rejected and
produces no mark. This validates the important generation-time rule: choose from an allow-list of
semantic zones and reject forbidden zones before rendering; no screenshot plus large-model
inspection loop is required.

### 6. Five-candidate diversity

![Five-candidate diversity](../../../public/assets/appearance-experiments/phase-2/06-five-candidate-diversity.png)

Each species produces five visibly different candidates by combining coat colors, region layouts,
slot assignments, and marks. This validates the immediate adoption requirement that the five
cards can be made distinct. It is not a statistical guarantee that thousands of candidates will
never look similar: that later scale requires a visible-key history plus a perceptual similarity
check or stricter palette/layout quotas.

## Decision and next boundary

The experiments pass as a technical feasibility layer for all five requested controls:

1. large natural-region color blocks;
2. color-slot permutations;
3. local marks;
4. generation-time safe zones;
5. five-candidate visible diversity.

The current product-safe boundary is:

- keep Phase 1 source-texture relative recoloring as the accepted visual foundation;
- keep dog and fox on one shared appearance protocol with species-specific region definitions;
- do not adopt the rejected UV-mask assets or the fixed-camera image-space masks as production
  runtime behavior yet;
- when implementation is approved, promote only reviewed semantic/UV region assets and add
  automated tests for forbidden zones, slot compatibility, deterministic keys, and multi-angle
  rendering.

## Evidence inventory

The six individual plates above are checked-in under
`docs/public/assets/appearance-experiments/phase-2/`. The larger combined plate is also retained
as `phase-2-all-stages.png`; the individual plates are the authoritative review artifacts because
their widths match the number of candidates in each experiment.
