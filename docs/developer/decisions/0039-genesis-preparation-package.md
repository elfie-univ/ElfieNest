# ADR-0039: Register the Genesis preparation package without activating it

- **Status:** accepted
- **Date:** 2026-09-22
- **Scope:** configuration placement and preparation-package integrity

> The draft-only publication gate below is superseded by [ADR-0040](./0040-genesis-source-publication-before-activation). The inventory and no-dual-read decisions remain.

## Decision

Keep reviewed preparation data under `config/genesis/`, not an ignored build
directory. Register `program.yaml`; enumerate all other files through its exact,
hash-bound manifest. Inspection validates technical integrity, not life semantics.
The inspector rejects published status until a separately verified publication
and typed-consumer implementation exists.

Current production world/species readers remain unchanged. No dual read, fallback,
new creation engine or runtime source dependency is introduced. The later cutover
must retire old creation inputs while preserving required runtime appearance assets.
Missing geography, course evidence or unresolved policy remains a publication
blocker rather than a default invented by a loader.

## Consequences

Package location is durable and discoverable. Configuration inventory remains
closed: manifest members are enumerated, not excluded by directory allowlists.
Draft integrity and production readiness are distinct checks. Configuration 1.5
records this preparation boundary; semantic ownership remains with Elfie Genesis.
