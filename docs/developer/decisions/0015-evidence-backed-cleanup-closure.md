# ADR-0015: Cleanup closure requires inventory and residual evidence

- **Status:** Accepted
- **Date:** 2026-08-14
- **Scope:** Repository-wide cleanup claims, conformance closure and guarded source scopes

## Context

Several migrations passed selected tests and were reported as complete even
though the approved target had not been compared with the complete source tree.
Unclassified directories, compatibility shells, old callers and Godot
developer/export material remained. Tests proved only the behaviors they
asserted; they did not prove that every requested path had been inventoried or
that every replaced route had disappeared.

The conformance lifecycle had a second gap. The governance change classifier
excluded deleted paths, and candidate-only registry tests could not inspect a
register after both its file and registration were removed. An open or
unproved register could therefore disappear without a base-branch rejection.

## Decision

A passing test, build, clean worktree or successful push is never sufficient
evidence for a cleanup-complete or contract-conformant claim.

Every cleanup slice must compare the approved target with a recursive inventory
of its exact scope, including tracked, untracked, ignored and empty paths. Every
path is classified as target source, retained content, developer input,
generated material, current conformance debt or a proved deletion candidate.
The review also traces imports, dynamic launch targets, scenes/resources,
export inputs, CLI/scripts and documentation references as applicable. It
reports completed, retained and remaining items separately.

A conformance row newly marked `closed` carries one compact evidence cell with
all of these stable fields:

- `target=` — exact governing clause or accepted disposition;
- `inventory=` — the reviewed source/runtime scope;
- `references=` — caller, scene, export and replacement-route proof;
- `verification=` — positive and negative behavior checks;
- `residuals=` — zero relevant residuals or an explicit out-of-scope statement.

Tests alone cannot satisfy all five fields. Human review validates their
meaning; the governance checker validates their presence and status transition.

The immutable base-branch checker now includes deletions, compares base and
candidate conformance registrations, requires bilingual status parity and
rejects removal unless every base row is closed with complete evidence. An
all-closed register may remain registered only briefly with an explicit
`Closure state: ready` marker so the final product change can pass before a
separate governance-only removal. The removal must delete both language files
and their registrations without product files.

Contract-guarded cleanup roots additionally use a structural scope scanner.
Every direct structural entry must be classified; unknown entries fail. Paths
owned by an open cleanup row may shrink or be edited but cannot gain new files.
Closing that row while one of its temporary paths remains is rejected.

## Consequences

Future cleanup work has a visible definition of done that cannot be replaced by
running a convenient test subset. The scanner cannot prove semantic usefulness,
so maintainer review remains necessary, but it prevents unreviewed directories
and base-register deletion from becoming invisible.

The evidence is kept in the conformance row rather than a separate session log
or workflow ledger. Once the register is validly removed, permanent structural
and dependency gates remain. Adding a legitimate new structural category
requires a governance review instead of silently expanding a catch-all folder.
