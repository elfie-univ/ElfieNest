# ADR-0023: Tiered validation and exact-snapshot reuse

- **Status:** Accepted
- **Date:** 2026-08-16
- **Scope:** local commit, feature-branch push and protected-main validation

## Context

The complete pre-submit gate is the correct final release backstop, but running
it for every ordinary commit repeats unrelated tests and toolchain work. The
repository needs a smaller safe loop without allowing a local pass to weaken
the immutable-base or protected-main checks.

## Decision

- Classify the candidate from changed paths and select G1 commit, G2 push or G3
  main validation. Unknown executable paths, governance, toolchain, lockfile and
  delivery changes automatically escalate to G3.
- G1 runs changed-file diff/secret/quality checks, deterministic affected tests
  and task-closure `progress`. G2 adds the quality baseline and affected API,
  persistence, architecture or documentation integration checks. G3 keeps the
  existing complete `pre_submit_gate.sh` and task-closure `complete` check.
- Reuse only successful deterministic results for an exact candidate snapshot.
  The key covers the rule/check version, stage, base SHA, candidate content,
  lockfiles, toolchain and selection rules. A post-run fingerprint mismatch
  invalidates the result; failures and live-provider evidence are not cached as
  passes.
- Cache records remain in ignored `build/validation-cache/`, use atomic writes
  and contain no source or secret material. GitHub CI still evaluates the latest
  commit SHA and remains authoritative for protected branches.

## Consequences

Ordinary commits complete with focused feedback, while Provider/model changes
select their API, persistence and validation tests instead of the whole suite.
Governance and unknown changes intentionally remain expensive. The full gate is
run once per exact candidate when a previous successful result can be reused;
it is never bypassed for main-branch delivery.
