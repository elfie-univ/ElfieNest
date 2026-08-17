# ADR-0024: Explicit local checkpoints for unavailable platform acceptance

> Superseded on 2026-08-17. External-environment gaps remain explicit open
> Conformance residuals; no task-specific local exception flag is retained.
> This ADR is kept as decision history.

- **Status:** Superseded
- **Date:** 2026-08-16
- **Scope:** historical local checkpoints for unavailable platform acceptance

## Historical record

The former local exception separated unavailable host evidence from local code
failures. It was removed with the per-task closure mechanism. External host gaps
are still recorded as open Conformance residuals and must be supplied by CI or a
matching host before protected delivery; no local flag converts them to success.
