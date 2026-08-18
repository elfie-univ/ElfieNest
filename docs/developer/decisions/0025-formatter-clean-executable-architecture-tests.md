# ADR-0025: Keep executable architecture tests formatter-clean

- **Status:** accepted
- **Date:** 2026-08-17
- **Scope:** repository quality and architecture-test maintenance

## Context

The current main branch contains existing Ruff format diagnostics in an
executable architecture test. Because that test is part of the governance
surface, the normal quality baseline cannot be closed while the file remains
unformatted. The required repair is mechanical and does not change assertions,
validation rules, or architecture baselines.

## Decision

Executable architecture tests remain subject to the pinned Ruff formatter. A
format-only repair may be delivered as a governance-only change when it leaves
the test behavior, rule inputs, and baseline entries unchanged. Any semantic
change to an architecture rule still requires its own bilingual ADR and must
remain separate from product implementation.

## Consequences

The repository can keep the quality baseline at zero new formatter diagnostics
without weakening governance coverage or adding an exemption. A formatter-only
governance commit may be reviewed independently from Provider or product
changes.

Rejected alternatives are excluding architecture tests from formatting,
recording the diagnostics as permanent debt, and mixing a governance repair
with product implementation.
