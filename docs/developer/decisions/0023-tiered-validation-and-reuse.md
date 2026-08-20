# ADR-0023: Tiered validation and check-scoped evidence reuse

- **Status:** Accepted
- **Date:** 2026-08-16
- **Revised:** 2026-08-20
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
- Run the formatting and static-analysis fast lane before every tier and before
  any test or other expensive check. Before freezing a local submit candidate,
  preparation may use the Ruff formatter to modify only in-scope dirty or
  untracked `.py` and `.pyi` files. It refuses a file that has both staged and
  unstaged changes. Commit hooks, tests and CI are check-only and never format
  files.
- After the fast lane, G1 runs the staged secret check and deterministic
  affected tests. G2 adds the quality baseline and affected API, persistence,
  architecture or documentation integration checks. G3 keeps the existing
  complete `pre_submit_gate.sh` backstop. Within one selected-tier invocation,
  the repository-wide quality baseline runs at most once: G1 and the commit
  hook omit it, while G2/G3 invoke it directly rather than through an umbrella
  hook. The backstop also reuses an existing pnpm installation when its module
  metadata and manifest/lock inputs match the base; missing or changed inputs
  may install once, and a network failure stops without a broader retry.
- Treat a tier as a set of required checks, not as part of a test check's identity.
  Key reusable deterministic test checks by their command, scoped input contents and
  modes, relevant immutable base, and local tools. This lets G2 consume a G1
  focused-test pass without starting the same command again.
- Partition the local G3 pytest backstop into conservative registered top-level
  bundles. A reusable bundle requires its pass record, coverage fragment,
  artifact digest, matching coverage/pytest versions and readable coverage
  data; its input set also follows the tests' local Python import closure and
  shared `conftest.py` imports. G3 combines all fragments and applies the
  repository threshold once. A prior complete-bundle run uses the same
  evidence, while a narrower node or file cannot prove a larger bundle.
  Unknown executable inputs invalidate all bundles.
- Refine the App bundle into registered Bootstrap, Feature/Configuration,
  Interface, Orchestration and product-E2E module slices. Each slice follows
  declared source roots plus its static import closure and explicit dynamic or
  resource inputs. Bind bundle evidence to the immutable base SHA, normalize
  coverage paths to repository-relative names before storage, and reject
  non-portable fragments so exact content can be reused by candidate trees or
  other worktrees without mixing source paths.
- Keep exact-candidate reuse, and give the remaining expensive G3 backstop a
  separate fingerprint. Source, tests, dependencies, toolchains, documentation
  and gate rules remain fail-closed backstop inputs; only paths explicitly
  handled as generated or ignored by the cache rules are excluded.
- A fast-lane failure stops before tests and expensive checks. After any later
  failure, rerun the exact failed node first and expand to its owning module and
  affected integration only when the repair or dependency boundary requires
  it. A failure never automatically restarts a broader gate or already-proven
  checks. Run a complete G3 backstop once for the final executable candidate,
  not after every repair edit.
- The keys cover rule/check version, base SHA, selected candidate content,
  local toolchain and relevant execution environment. One invocation shares a
  repository snapshot across bundles, but verifies current signatures before
  accepting a hit. A post-run fingerprint mismatch invalidates the result;
  failures and live-provider evidence are not cached as passes. The direct
  main backstop reuses valid bundles. `--no-cache` changes only whether valid
  evidence may be read: it never changes the selected tier or adds checks that
  the tier does not require.
- Cache records remain in ignored `build/validation-cache/`, use atomic writes
  and contain no source or secret material. Failures are never passes, and a
  forced same-key failure removes older evidence. GitHub CI still evaluates the
  latest commit SHA and remains authoritative for protected branches.

## Consequences

Ordinary commits complete with focused feedback, while Provider/model changes
select their API, persistence and validation tests instead of the whole suite.
Formatting defects are fixed safely or reported before any test starts, and
non-local execution surfaces remain check-only.
An unchanged test package passed during implementation is no longer repeated at
commit, push or local G3 merely because the stage changed. Narrow repair checks
stay narrow and cannot satisfy broader coverage. Governance and unknown changes
remain fail-closed. Latest-SHA CI remains mandatory for protected delivery.
