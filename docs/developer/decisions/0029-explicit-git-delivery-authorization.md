# ADR-0029: Explicit Git action authorization and one-PR delivery

- **Status:** Accepted
- **Date:** 2026-08-23
- **Scope:** Coding-Agent Git authorization, Pull Request lifecycle and candidate evidence reuse

## Context

ElfieNest previously generalized a useful rule—do not repeatedly confirm steps
inside an action the user already authorized—into an unsafe rule that allowed an
approved implementation plan to authorize commit, push, Pull Request creation
and main merge as one chain. At the same time, the governance classifier treated
a local review boundary as a mandatory Pull Request boundary. One script-layout
task consequently crossed main through seven Pull Requests even though it was
one user-visible task and one final acceptance boundary.

This was neither required by affected-test quality nor scalable under concurrent
development. A Pull Request is a main-mutation proposal, not a checkpoint for
every local commit. Plans, ADRs, skills and historical context describe work but
cannot grant external write authority.

## Decision

- Use six explicit action levels: implementation permits local work and
  reasonable local commits; commit remains local; push updates only the current
  feature branch; create-PR creates or reuses one PR and stops; merge-main uses
  that one PR, CI and the native merge queue; completion/delivery alone grants
  no Git action.
- Bind authorization to the current task, repository, branch, action and frozen
  candidate SHA. It is consumed by success or cancellation and expires when the
  target, scope or candidate changes. A merge-queue synthetic SHA is not a new
  candidate.
- Keep a feature branch across conversations and days when useful. Multiple
  focused commits and pushes do not create a Pull Request. One explicit
  main-delivery request creates or reuses at most one PR. Multiple PRs require
  advance approval of the exact count and boundaries.
- Separate local commits by review responsibility when that improves review,
  but allow governance-sensitive and product commits in one final PR when the
  product still passes the immutable base rules. A product change that depends
  on relaxing those base rules remains rejected and can use multiple PRs only
  through the explicit exception above.
- Split branch push/recovery from main delivery. The ordinary Git skill contains
  no PR, queue or main mutation. The narrow main skill handles create-only and
  merge-main modes, freezes one head SHA, checks live rules and review, and
  dequeues when the user stops. Direct main push is unavailable in ElfieNest.
- Before the single PR is created for merge-main, validate the frozen SHA through
  the trusted main workflow. Publish reusable evidence only after all selected
  lanes and the aggregate gate pass. A PR may skip those lanes only when the
  exact candidate, base-governance fingerprint, Manifest version, candidate
  toolchain fingerprint and trusted workflow identity all match; otherwise it
  runs the selected graph normally.
- Measure the ten-minute delivery SLO from the user's release of a stable final
  candidate until that candidate is verified on main. The timer never restarts
  because an implementation was split into several PRs. CI records the portions
  it can observe; the delivery operator records the user-release boundary.
- Machine checks establish technical evidence, not user acceptance. Required
  UI, behavior or document review occurs before create-PR/main delivery, while
  local commits and feature-branch pushes remain available for iteration.

## Alternatives rejected

- **Let an approved plan authorize the whole Git chain:** removes prompts by
  erasing action boundaries and can mutate GitHub before acceptance.
- **Create a PR for every governance/product commit:** preserves small diffs but
  turns internal sequencing into repeated queue waits and moving-main churn.
- **Run pre-PR validation and then always rerun it after PR creation:** preserves
  evidence but doubles the dominant latency without changing the candidate.
- **Infer remote intent with a natural-language classifier:** adds another
  ambiguous authority source. Explicit commands and structural skill boundaries
  are simpler and auditable.

## Consequences

Most implementation conversations create no PR. Contributors can checkpoint and
share a feature branch without reserving main. Final delivery has one visible
candidate, one PR, one affected validation graph and one short queue mutation.

Evidence reuse adds a small trusted identity protocol and seven-day artifact.
Failure to prove any identity component is safe: the PR runs its selected lanes
instead of reusing evidence. A changed candidate requires a new user main action
rather than an automatic fix-and-requeue loop.

The source contract requires a live maintainer-review rule, but source files
cannot enable or prove that external setting. Until the live ruleset and an
actual non-author approval satisfy it, the narrow main skill fails closed; it
does not claim the review gate is active.
