# ADR-0023: Tiered validation and check-scoped evidence reuse

- **Status:** Accepted; protected-main G3 requirement partially superseded by ADR-0027
- **Date:** 2026-08-16
- **Revised:** 2026-08-22
- **Scope:** local commit, feature-branch push and protected-main validation

## Context

The complete pre-submit gate is the correct final release backstop, but running
it for every ordinary commit repeats unrelated tests and toolchain work. The
repository needs a smaller safe loop without allowing a local pass to weaken
the immutable-base or protected-main checks.

## Decision

ADR-0027 supersedes only this record's requirement that every protected-main
merge wait for a complete G3. Local affected validation, check-scoped evidence
identity and reusable full-test bundles remain active. The complete G3 now runs
after main acceptance and for manual/release validation.

- Classify local work from changed paths as G1 commit or G2 push validation.
  Unknown executable, governance, toolchain, lockfile and delivery changes
  fail closed by selecting every exact-candidate CI lane; they do not start the
  complete repository locally merely because a push begins.
- G1 runs changed-file diff/secret/quality checks and deterministic affected
  tests. G2 adds the quality baseline and affected API, persistence,
  architecture or documentation integration checks. Full mode keeps the
  existing complete `pre_submit_gate.sh` backstop for post-submit, manual and
  release execution.
- Treat a tier as a set of required checks, not as part of a test check's identity.
  Key reusable deterministic test checks by their command, scoped input contents and
  modes, relevant immutable base, and local tools. This lets G2 consume a G1
  focused-test pass without starting the same command again.
- Partition the full pytest backstop into conservative registered top-level
  bundles. A reusable bundle requires its pass record, coverage fragment,
  artifact digest, matching coverage/pytest versions and readable coverage
  data; its input set also follows the tests' local Python import closure and
  shared `conftest.py` imports. Full mode combines all fragments and applies the
  repository threshold once. A prior complete-bundle run uses the same
  evidence, while a narrower node or file cannot prove a larger bundle.
  Unknown executable inputs invalidate all bundles.
- Keep exact-candidate reuse, and give the remaining expensive full backstop a
  separate fingerprint. Source, tests, dependencies, toolchains, documentation
  and gate rules remain fail-closed backstop inputs; only paths explicitly
  handled as generated or ignored by the cache rules are excluded.
- After a failure, rerun the exact failed node first and expand to its owning
  module and affected integration only when the repair or dependency boundary
  requires it. Run a complete full backstop for the accepted main tip or an
  explicit release candidate, not after every repair edit.
- The keys cover rule/check version, base SHA, selected candidate content,
  local toolchain and relevant execution environment. One invocation shares a
  repository snapshot across bundles, but verifies current signatures before
  accepting a hit. A post-run fingerprint mismatch invalidates the result;
  failures and live-provider evidence are not cached as passes. The direct
  full backstop reuses valid bundles; `--no-cache` is propagated to force a
  clean replay.
- Cache records remain in ignored `build/validation-cache/`, use atomic writes
  and contain no source or secret material. Failures are never passes, and a
  forced same-key failure removes older evidence. GitHub CI still evaluates the
  latest commit SHA and remains authoritative for protected branches.

## Consequences

Ordinary commits complete with focused feedback, while Provider/model changes
select their API, persistence and validation tests instead of the whole suite.
An unchanged test package passed during implementation is no longer repeated at
commit, push or full backstop merely because the stage changed. Narrow repair
checks stay narrow and cannot satisfy broader coverage. Governance and unknown
changes remain fail-closed through all selected candidate lanes. Latest-SHA CI
remains mandatory for protected delivery.
