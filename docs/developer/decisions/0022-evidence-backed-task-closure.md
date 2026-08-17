# ADR-0022: Evidence-backed task closure and immutable two-phase governance

> Superseded on 2026-08-17. The per-task JSON matrix and its mandatory checker
> duplicated the Conformance registers and created repository-root merge noise.
> Current evidence lives in Conformance registers, change records, actual test
> results and CI artifacts; this ADR is retained only as decision history.

- **Status:** Superseded
- **Date:** 2026-08-16
- **Scope:** implementation completion, conformance closure and repository quality gates

## Historical record

The former per-task JSON matrix and mandatory checker were introduced to keep
runtime, platform and installation evidence visible. They were later removed
because the mechanism duplicated the Conformance registers, created root-level
merge conflicts and added no independent source of truth. The durable rule is
kept in the repository-governance contract: report actual checks, runtime
evidence and open external residuals separately.
