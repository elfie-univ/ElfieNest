# ADR-0004: App business domains and vertical migration slices

- **Status:** accepted
- **Date:** 2026-08-10
- **Scope:** `app/` business ownership and migration units

## Context

The App and system contracts already define dependency direction, Ports and
Adapters, Infrastructure capability packages, API resource scopes and the
composition root. The current `app/features/` and `app/orchestration/` trees,
however, are migration-state inventories rather than a final business map.
They contain actor-oriented groupings, empty placeholders, overlapping owners
and flat workflow files. Migrating those directories mechanically would retain
the same ambiguity behind new paths.

ElfieNest migrates incrementally and must remain usable after every merged
slice. A horizontal layer-by-layer move would leave partial call chains and
make it unclear which legacy implementation can be deleted. The final business
and workflow units therefore need to be fixed before product migration begins.

## Decision

App migration uses vertical slices. Each selected slice inventories its real
Interfaces and callers, establishes one public Feature facade, introduces only
the Ports required by that slice, implements them in the existing
Infrastructure capability packages, wires them in Bootstrap, migrates every
caller and deletes the replaced implementation before the slice closes.

The final Feature domains are:

- `accounts`, `adoption`, `communication`, `elfies`, `nest_management`,
  `setup`, `bodies` and `operations`;
- `configuration`, with independently migratable `providers`, `food`,
  `capabilities` and `settings` subdomains.

The final Orchestration workflows are `lifecycle`, `nest_session`,
`resident_admission`, `setup_installation`, `message_delivery`, `embodiment`
and `observer`. They are named for real cross-authority workflows rather than
mechanically mirroring every Feature.

`administration`, `chat`, `elfie_profile`, `nest_registration` and the current
Feature-level `embodiment` grouping are migration-state locations. Their
existing behavior is absorbed by the final owners named in the Application
contract; the decision creates no new product capability.

API remains versioned and organized by external business resource.
Infrastructure remains organized by the seven system capability packages and
does not mirror Feature directories. Bootstrap remains one composition root,
not a business layer or a separately migrated horizontal phase.

## Consequences

The Application contract is the normative target map. The Application
conformance register maps current locations to that target and records the
callers, deletion gates and machine debt for one approved slice at a time.
Target directories are created only when their slice starts; this decision does
not authorize empty placeholders, speculative Port methods, compatibility
layers, feature expansion or a repository-wide move.

Alternatives rejected are treating the current directory inventory as final,
organizing Features by page or actor role, mirroring every Feature in
Orchestration or Infrastructure, migrating one physical layer at a time, and
freezing a complete implementation order before each real call chain is
inventoried.
