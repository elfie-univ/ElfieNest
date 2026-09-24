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

Publication and availability remain separate decisions. A published package is
eligible for activation only after its typed Genesis consumer, semantic and
feasibility checks, and single-path cutover are verified. That cutover is now
complete for the current package: Adoption and Genesis load the published
`config/genesis/` package through the registered adapter, and the retired
world/species production paths are not read. The manifest still records
per-species activation blockers. Myelle remains in the package with catalog
status `draft` while its Godot role assets are missing; it cannot be offered for
adoption. Saevi/Tovren appearance review is author-accepted without a new render
run; the technical render record is not rewritten.

The App availability projection therefore selects only species in the activated
package whose creation rules, life-feasibility checks and runtime assets pass
validation. It never interprets source publication alone as permission to offer
candidates. Activation is a separate, verified handoff to the existing Adoption
→ ResidentAdmission → Elfie Genesis path, not a second creation path or an
administrator allowlist.

## Consequences

The preparation-only publication restriction in ADR-0039 is superseded by this
decision. The closed inventory, digest checks and no-dual-read rule remain.
Neither a published YAML status nor package integrity proves that every
semantic Genesis gate is complete: the remaining behavior and admission gaps
are tracked in ELF-019. A future package or species still requires its own
activation evidence; activation of one package does not make draft species
available.
