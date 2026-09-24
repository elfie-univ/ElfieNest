# ADR-0040: Publish Genesis sources before activating creation

- **Status:** accepted
- **Date:** 2026-09-24
- **Scope:** Genesis package publication and runtime activation boundary

## Decision

The author-reviewed, hash-bound `config/genesis/` bundle may be published as a
versioned source package before the product consumes it. Publication requires a
closed member inventory, matching entry/member/source digests, creator-source
section bindings, exact resident-unit projection and no unresolved knowledge
conditions. Publication freezes the source version; changed content needs a new
version.

Publication does not make the bundle an active creation source. Adoption keeps
using the existing world/species path until a typed Genesis consumer, semantic
and feasibility checks, and a single-path cutover are verified. The published
manifest records activation blockers separately. Myelle remains in the package
with catalog status `draft` while its Godot role assets are missing; it cannot be
offered for adoption. Saevi/Tovren appearance review is author-accepted without
a new render run; the technical render record is not rewritten.

The App availability projection therefore selects only an activated creation
package and species with validated creation rules and runtime assets. It never
interprets source publication alone as permission to offer candidates. Activation
is a separate, verified handoff to the existing Adoption → ResidentAdmission →
Elfie Genesis path, not a second creation path or an administrator allowlist.

## Consequences

The preparation-only publication restriction in ADR-0039 is superseded by this
decision. The closed inventory, digest checks and no-dual-read rule remain.
Neither a published YAML status nor package integrity proves production Genesis
behavior. The production cutover remains a separate implementation and gate.
