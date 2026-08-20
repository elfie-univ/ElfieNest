# Validation fast lane and run-history review

Status: current implementation snapshot, 2026-08-20.

This page records the repository's quality and validation-efficiency controls,
the evidence that has been verified, and the checklist for reviewing later
runs. It is a stable engineering guide, not a replacement for CI logs or a
machine-generated run ledger.

## What is in place

- **Format fast lane.** The commit/push gate checks diff formatting and focused
  Ruff rules before tests. `--fix-format` writes only dirty or untracked Python
  files in scope; mixed staged/unstaged files stop instead of being rewritten.
  A format failure starts no broader test gate.
- **Tiered delivery.** `commit` uses G1, feature-branch `push` uses G2, and
  main/release, governance, toolchain or unknown-impact changes use G3. The
  selected tier is not changed by `--no-cache`.
- **Scoped reusable evidence.** Deterministic checks are keyed by the immutable
  base commit, candidate inputs, command identity and local toolchain. Failed
  results are never stored as passes. The G3 pytest backstop contains the
  repository bundles plus 25 App module slices; static local-Python imports and
  explicit dynamic/resource inputs determine each slice's scope.
- **Portable coverage.** Coverage fragments are normalized to repository-relative
  paths, checked for readability and metadata, and rejected when they contain
  an unsafe path. The full threshold is enforced once after all required
  fragments are combined.
- **Submission authority.** The Git submission skill routes the standard
  commit/push/main workflow through `scripts/pre_submit_gate.sh` and uses
  terminal Git only. The pre-commit hook remains check-only for Gitleaks; a raw
  `git commit` is not a substitute for the tiered gate.

## Verification snapshot

The following evidence was reproduced for the 2026-08-20 phase-two candidate.
It demonstrates the mechanism; it is not a promise of a fixed speedup for
every repository change.

| Evidence | Result |
| --- | --- |
| Final local G3 | Passed; combined coverage 79.32% |
| App setup bundle, cold → warm | 4.11 s for 3 tests → 1.19 s; second run reused the pass and did not start pytest |
| App CLI bundle, cold → warm | 44.91 s for 188 tests → 2.51 s; second run reused the pass |
| Fingerprint input scope | Old single App scope: 1,570 files; current setup: 328; current CLI: 609 |
| Focused gate/bundle regression tests | 61 passed after the coverage-path fix |

The commits containing this implementation are `81a2a388` (phase-two
governance) and `88732411` (implementation and coverage/CLI fixes).

## Standard review command

Use the controlled entry point so the result can be reused by a later gate:

```bash
git fetch --prune origin main
bash scripts/pre_submit_gate.sh --stage commit --fix-format \
  --base-sha "$(git rev-parse origin/main^{commit})"
```

For a direct bundle experiment, run the same selector twice with one cache
root and compare the output and `real` time:

```bash
CACHE=$(mktemp -d /private/tmp/elfienest-validation.XXXXXX)
time .venv/bin/python3 scripts/architecture/validation_test_bundles.py \
  --selectors test/app/features/setup \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --cache-root "$CACHE"
time .venv/bin/python3 scripts/architecture/validation_test_bundles.py \
  --selectors test/app/features/setup \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --cache-root "$CACHE"
```

The first run should report an executed bundle; the second should report
`reused passed test bundle` and must not start pytest. Raw `pytest` remains a
diagnostic command and does not create submission-cache evidence.

## What to inspect in later run history

For each recent run, capture these fields before comparing timings:

1. candidate SHA, immutable base SHA, stage and requested selectors;
2. executed bundles versus reused bundles and each bundle's wall time;
3. format, quality, test, coverage and documentation commands that ran;
4. exact failure, retry count and whether any failed result was accepted;
5. toolchain/platform and cache-root identity.

Review the records for four patterns:

- the same key running more than once without an input, toolchain or base change;
- a full G3 starting after a format-only failure;
- an unchanged bundle being invalidated by an over-broad input or Worktree path;
- a failure being written or read as a passing cache record.

When a pattern appears, first reproduce one exact command, then inspect the
bundle input closure and cache key. Do not infer a speedup from a warm cache
alone; compare a cold run and a same-key warm run on the same candidate.

## Evidence boundaries and follow-up

- `build/validation-cache/` is ignored, local evidence. It can explain local
  reuse, but it cannot replace CI evidence for a new commit SHA.
- The default cache root is per Worktree. Cross-Worktree reuse requires an
  explicitly shared `ELFIENEST_VALIDATION_CACHE_ROOT`; an automatic central
  resolver is not yet implemented.
- Current remote CI still runs the full Python test command on candidate pushes;
  remote bundle-level artifact reuse is not yet wired.
- Cache records currently do not form a durable, centralized duration history,
  and this repository cannot automatically ingest every future Codex chat
  transcript. A future monitoring improvement should emit a small structured
  JSONL run summary (candidate/base, selected/reused bundles, durations,
  failures and retry reason) and retain it as a local or CI artifact.

When asked to review recent validation history, use this page as the checklist,
then inspect the supplied command output, cache records and CI artifacts. Report
separately: verified reuse, unnecessary repetition, invalidation causes,
environment blocks and the next smallest optimization.
