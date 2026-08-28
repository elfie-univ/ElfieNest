# ADR-0023: Tiered validation and check-scoped evidence reuse

- **Status:** Partially superseded by ADR-0027; check-scoped evidence reuse remains active
- **Date:** 2026-08-16
- **Revised:** 2026-08-23
- **Scope:** local commit, feature-branch push and protected-main validation

## Context

The complete pre-submit gate is the correct final release backstop, but running
it for every ordinary commit repeats unrelated tests and toolchain work. The
repository needs a smaller safe loop without allowing a local pass to weaken
the immutable-base or protected-main checks.

## Decision

ADR-0027 supersedes both the protected-main G3 prerequisite and the requirement
to map every ordinary commit/push action to a mandatory local G1/G2 tier. The
check-scoped evidence identity, controlled affected-test runner and reusable
full-test bundles in this record remain active.

- Use a repository-managed pre-commit hook for the real staged snapshot. It
  runs diff whitespace, pinned Gitleaks and staged Python Ruff only, targets a
  warm duration of 20 seconds, and performs no tests, MyPy, Node, Godot, fetch
  or network work. Do not add a test-bearing pre-push hook.
- Keep `--stage commit` as an explicit reusable local checkpoint and
  `--stage push` as an optional affected-integration replay. Neither command is
  an ordinary feature push prerequisite. Local development selects focused
  checks from changed behavior, not from a subjective task-size label.
- Move authoritative candidate selection to immutable-base CI. Python changes
  select affected test bundles and the independent full Python quality lane in
  parallel; unknown executable, governance, toolchain, lockfile and delivery
  changes select every exact-candidate lane fail-closed.
- Treat every root or nested `AGENTS.md` as governance input. Local affected
  validation selects only its direct governance and architecture checks, while
  the exact PR candidate still selects every lane. A rule-only edit under a
  product directory therefore cannot start that product's local test suite.
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

Ordinary commits stay seconds-long and ordinary pushes no longer wait for a
second local integration stage. Provider/model changes still select their API,
persistence and validation tests, while Python quality runs independently on
the same exact PR head. An unchanged test package passed during development is
not repeated merely because an explicit local stage name changed. Narrow repair
checks stay narrow and cannot satisfy broader coverage. Governance and unknown
changes remain fail-closed through all candidate lanes, and latest-SHA CI
remains mandatory for protected delivery.
