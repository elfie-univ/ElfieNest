# ADR-0019: Configuration-driven species packages

- **Status:** Accepted
- **Date:** 2026-08-15
- **Scope:** species registration, presentation assets, Genesis inputs and Godot appearance bindings

## Context

Species metadata, appearance defaults and Genesis inputs had been split between
Profile-owned constants, frontend image files and Godot-specific mappings. That
made adding a species require edits in several unrelated authorities and made a
missing presentation asset easy to overlook. Candidate names also had no place
in a species definition because they are generated during Adoption.

## Decision

Use `config/species/catalog.yaml` as the fixed bundled registry and one
`config/species/<package>/` directory per species. A package owns its canon link,
display metadata, supported appearance controls and ranges, Genesis inputs, and
the distinct `headshot.png` and `full-body.png` presentation assets. The
catalog is loaded and validated by Infrastructure, then injected as a typed
immutable value into Profile, Genesis and Adoption.

The status rules are explicit: `published` is adoptable only after the complete
package and Godot package pass validation; `retired` remains resolvable for
existing profiles but is not adoptable; `draft` is omitted from runtime
options. The frontend receives the active species list and image URLs from the
API and keeps no species or image authority. Godot remains the only 3D body and
rendering authority; its schema-v2 manifest owns semantic-to-bone bindings.

## Consequences

- Adding a species is primarily adding a validated package and matching Godot
  package, not editing Profile or frontend allowlists.
- Missing fields, missing/invalid PNGs, duplicate presentation images and
  incomplete Genesis data fail closed before release.
- Existing profiles can still resolve a retired species without reopening it for
  Adoption.
- A future appearance protocol change requires a manifest/config protocol
  version update and focused Godot/Python validation.
