# ADR-0027: Exact-candidate merge gates and post-submit full validation

- **Status:** Accepted
- **Date:** 2026-08-22
- **Scope:** Pull Request routing, merge queue, main health and release validation
- **Supersedes:** the protected-main G3 prerequisite in ADR-0023

## Context

ElfieNest made the complete repository backstop a prerequisite for every main
delivery. Small frontend and documentation changes therefore paid for unrelated
Python, Godot, toolchain and docs work locally, while any unrelated red test
blocked all contributors. Repeatedly merging a moving main into a validated
candidate also invalidated evidence and created an endless retry loop under
concurrent development.

Large projects do not reserve main while each contributor runs the whole
repository. Mature affected-test systems validate candidates in parallel,
serialize only the final mutation, run a short exact-merge check and retain
broad post-submit, nightly and release coverage. OpenClaw's trusted preflight,
aggregate check and main-parity model is the primary operational reference;
GitHub's native merge queue supplies ElfieNest's exact synthetic merge.

## Decision

- Bind merge-blocking evidence to the exact Pull Request head SHA. Use the
  classifier from the immutable base commit to emit a versioned affected-path
  manifest. Unknown executable and governance/toolchain changes select all
  lanes; security-fast always runs.
- Run selected Python, web, Desktop, Developer Tools, architecture,
  persistence, Godot, docs and toolchain lanes in parallel. Aggregate them as
  `elfienest/ci-gate`, then publish only the event-stable
  `elfienest/merge-gate` to branch protection. On Pull Requests that required
  check waits for the aggregate; on merge groups the same check name performs
  the lightweight synthetic-merge validation. The aggregate rejects missing,
  skipped, cancelled or failed selected lanes.
- Do not rebase or rerun affected tests merely because main advanced. A new
  candidate SHA or an actual conflict is the invalidation boundary.
- Use GitHub's native `merge_group` event for `elfienest/merge-gate`. Start with
  one Pull Request per group. The merge gate checks exact identity, base/ref,
  parents, diff cleanliness and gate schema; it installs no dependencies and
  reruns no product suites.
- Run the complete G3 after every main push and on explicit full/release
  dispatches. Main runs are non-cancelling and use two parity slots that retain
  running work while coalescing obsolete pending tips. Superseded PR heads may
  cancel.
- Quarantine ordinary merges after the newest main tip has a terminal red full
  backstop. Permit only an audited, narrowly scoped fix or revert until a newer
  green main result supersedes the red state.
- Require a live GitHub ruleset with Pull Requests, merge queue, stable checks,
  no direct/force pushes and maintainer review for governance/CI. Repository
  source alone cannot claim that external state is active.

## Alternatives rejected

- **Keep full G3 before every merge:** preserves broad coverage but violates the
  ten-minute delivery objective and propagates unrelated failures.
- **Continuously merge/rebase current main into each candidate:** turns normal
  main movement into evidence churn and does not scale with contributors.
- **Build a custom landing service now:** can provide an App-owned exact-merge
  check, but adds credentials, deployment and recovery ownership that GitHub's
  native merge queue already covers for the current repository.
- **Remove broad validation:** improves latency by losing detection. The full
  backstop is moved, not weakened.

## Consequences

Ordinary changes wait only for their affected evidence and a seconds-long
synthetic merge check. Medium and large work performs its required evidence on
the exact candidate during development instead of after the submit command.
Main can temporarily contain a regression detected by post-submit validation;
quarantine plus focused fix/revert is the explicit containment mechanism.
Platform outages remain outside the SLO and must be reported rather than
bypassed.

Cutover requires shadow replay over representative history, zero known missed
lanes, p95 timing within the contract, and verified live rules. Until then the
legacy full entry remains available and the ruleset stays in evaluation.
