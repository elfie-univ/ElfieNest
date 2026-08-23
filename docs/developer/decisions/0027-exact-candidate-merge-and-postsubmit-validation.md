# ADR-0027: Exact-candidate merge gates and post-submit full validation

- **Status:** Accepted
- **Date:** 2026-08-22
- **Revised:** 2026-08-23
- **Scope:** Pull Request routing, merge queue, main health and release validation
- **Supersedes:** ADR-0023's protected-main G3 prerequisite and mandatory ordinary local G1/G2 delivery stages

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
- Install a repository-managed staged-only pre-commit hook. Its warm path runs
  diff whitespace, pinned Gitleaks and staged Python Ruff within 20 seconds and
  has no tests, MyPy, Node, Godot, fetch or network work. Ordinary push has no
  test-bearing pre-push gate; explicit affected local stages remain diagnostic
  tools rather than delivery prerequisites.
- Treat the locked development tools and the managed hook as source-development
  readiness. The normal launcher repairs a missing hook through the existing
  idempotent `ensure --tier=dev` path; a non-Git source archive skips hook setup,
  and a clone is never assumed to have executed repository code automatically.
- Run selected Python, web, Desktop, Developer Tools, architecture,
  persistence, Godot, docs and toolchain lanes in parallel. Aggregate them as
  `elfienest/ci-gate`, then publish only the event-stable
  `elfienest/merge-gate` to branch protection. On Pull Requests that required
  check waits for the aggregate; on merge groups the same check name performs
  the lightweight synthetic-merge validation. The aggregate rejects missing,
  skipped, cancelled or failed selected lanes.
- Split Python correctness and Python static quality: affected deterministic
  tests and the full Ruff/format/MyPy baseline are separate parallel lanes.
  Python source/tests select both; pure frontend changes do not select Python
  quality unless governance/toolchain/unknown classification fails closed.
- Do not rebase or rerun affected tests merely because main advanced. A new
  candidate SHA or an actual conflict is the invalidation boundary.
- Use GitHub's native `merge_group` event for `elfienest/merge-gate`. Start with
  one Pull Request per group. The merge gate checks exact identity, base/ref,
  parents, diff cleanliness and gate schema; it installs no dependencies and
  reruns no product suites.
- Run the complete graph after every main push and on explicit full/release
  dispatches by selecting every existing lane in parallel, including Python
  bundles and quality, Web, Desktop, Developer Tools, architecture,
  persistence, Godot, docs, toolchain, release and runtime smoke. Each main
  lane uses two non-cancelling parity slots that retain running work while
  coalescing obsolete pending tips. Superseded PR heads may cancel.
- Record candidate and full-graph elapsed time in CI summaries. Budget local
  finalize/push at one minute, candidate CI at seven minutes and queue plus
  merge/ref verification at two minutes. The ten-minute p95 is conditional on
  sufficient external runner capacity; lack of capacity is an operational
  blocker, never a reason to skip a selected lane.
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
synthetic merge check. Broader work performs its required evidence on the exact
candidate during development and selected CI lanes instead of after the submit
command.
Main can temporarily contain a regression detected by post-submit validation;
quarantine plus focused fix/revert is the explicit containment mechanism.
Platform outages remain outside the SLO and must be reported rather than
bypassed.

The one-PR merge group intentionally does not rerun every product suite on the
synthetic merge. Semantic interference between two individually green changes
therefore cannot be reduced to zero without restoring long queue-time tests.
The seconds-long identity check, complete asynchronous main graph and immediate
quarantine are the accepted containment; this residual must not be described as
proof that concurrent semantic conflicts are impossible.

Cutover requires zero known missed lanes, timing telemetry within the contract,
verified live rules and sufficient runner capacity. The explicit local full
entry remains available for release/diagnosis but is not an ordinary push gate.
