# Testing & quality

## Full-suite environment preflight

Before starting the repository-wide pytest gate, check whether the current
host can bind a loopback socket:

```bash
uv run --no-sync python scripts/quality/checks/environment.py
```

The preflight does not skip or downgrade any test. It returns:

- `0`: loopback binding is available; run `pytest test/` once;
- `2`: the sandbox or host policy denied `127.0.0.1:0`; do not run the full
  suite in that environment, and run the same full command once with host or
  elevated permissions;
- `1`: an unexpected probe error; diagnose it before starting the full suite.

The gateway restart test remains part of the full suite. A permission-denied
preflight is an execution-environment result, not a reason to exclude that
test or to rerun the entire suite after an isolated retry.

## Test layers

```bash
uv run --no-sync pytest test/<changed-module>/
uv run --no-sync pytest test/architecture/
# Run this only after the preflight above returns 0.
uv run --no-sync pytest test/
```

The test directory mirrors the source. The root `test/` does not hold test
files directly; the architecture tests guard directory boundaries, legacy
package names, reverse dependencies and engineering-config contracts.

## CI and test-failure triage

A red check is evidence to investigate, not an instruction to change the
nearest assertion. Before changing production code, a test, CI, a scanner or a
quality baseline, establish the failure's cause in this order:

1. Record the exact workflow job, command, failing assertion and first relevant
   traceback. An email title or a red summary card is not sufficient evidence.
2. Read the governing contract, current configuration and the relevant tests.
   Then inspect history when the code looks surprising, especially for lazy
   imports, fallbacks, adapters, fixtures and boundary exceptions. Recover the
   original motivation before deciding whether to remove or replace behavior.
3. Trace the real call, data and dependency flow to its authority. Include
   dynamic imports, `python -m`, subprocesses and scanner targets; a dependency
   hidden behind a lazy import is still a dependency.
4. Classify the failure before editing:

   | Classification | Required response |
   | --- | --- |
   | Implementation regression | Restore the intended behavior with a regression test, then make the smallest production fix. |
   | Stale test fixture or expectation | Confirm the current contract first; update only the fixture or expectation that describes the accepted contract, and keep the behavior assertion. |
   | Incomplete contract migration or missing wiring | Complete ownership and injection at the composition boundary; do not revert the target contract or add a hidden fallback. |
   | CI/toolchain/environment failure | Reproduce the environment condition and fix the repository setup when it violates the project contract; otherwise report it separately without excluding the product test. |
   | Unconfirmed cause | Do not claim the problem is fixed; gather the missing evidence first. |

5. Add or restore a positive behavior test and, when a required dependency is
   involved, a negative fail-fast test. Never delete tests, add broad skips or
   xfails, widen a quality baseline, use `--no-verify`, or replace a real
   result with an empty/default fallback merely to turn the check green.
6. Verify in layers: focused behavior tests, affected architecture/scanner
   checks, quality and secret gates, then the appropriate broader suite. State
   separately which checks passed, which were not run, and which are blocked by
   the environment. A locally green subset does not prove remote CI is green.

The repair summary must identify the classification, the recovered design
motivation, the behavior deliberately preserved, the evidence run, and every
remaining residual risk. This keeps a test failure from becoming a blind
assertion change or a silent loss of a product feature.

## Architecture-governance checks

```bash
uv run --no-sync python scripts/governance/boundaries/app_layers.py \
  --project-root . --mode deny-all
uv run --no-sync python scripts/governance/boundaries/system_layers.py \
  --project-root . --mode deny-all
uv run --no-sync pytest test/architecture/
```

App and system scanner debt is zero, so both permanent scanners run in
`deny-all` mode without legacy baselines. If a future approved migration needs
a temporary exact baseline, it must shrink with each slice and be deleted when
it reaches zero. CI also evaluates candidate production code with the rules
from the pull request base commit, so a change cannot weaken the rule that
judges itself. See the
[repository architecture governance contract](../contracts/repository-governance).

## Quality gate

```bash
uv run --no-sync python scripts/quality/checks/python_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit uv run --no-sync pre-commit run --all-files
```

The quality baseline only admits already-existing diagnostics; any new Ruff,
format or MyPy diagnostic must be fixed — never hidden by widening ignores or
rewriting the baseline.

## Affected validation and full backstop

Install the staged-only commit hook once per clone/worktree setup:

```bash
bash scripts/quality/hooks/install.sh
```

Development runs focused tests before staging. `git commit` then checks only
the real staged snapshot: diff whitespace, pinned Gitleaks, and Ruff
check/format for staged Python files. The warm target is 20 seconds. The hook
does not run tests, MyPy, pnpm, Godot, fetch, or any network operation, and no
test-bearing pre-push hook is installed.

An ordinary push starts immediately after that hook. The exact PR head is
routed by the immutable-base manifest; security-fast, affected Python tests,
the full Python quality baseline and the other selected lanes run in parallel
and aggregate as `elfienest/ci-gate`. Main movement alone does not invalidate
that head. The native merge queue then runs the seconds-long
`elfienest/merge-gate` on the synthetic merge. `--stage commit` remains an
explicit reusable local checkpoint and `--stage push` an optional affected
integration replay; neither is an ordinary push prerequisite.

Successful deterministic test checks are keyed by command, scoped input contents and
file modes, the required immutable base, and local tools—not by delivery tier.
The full post-submit/release Python backstop is split into the registered top-level packages `app`,
`architecture`, `devtools`, `e2e`, `elfie`, `godot`, `infrastructure`, `nest`
and `scripts`. It runs only missing or invalidated bundles. Bundle inputs include
the transitive local Python imports of their tests and shared `conftest.py`
fixtures; reuse additionally requires a matching pass record, coverage fragment
digest/version and readable coverage data. One invocation shares a repository
snapshot and rechecks signatures before accepting a hit. It then combines every
fragment and enforces the repository coverage threshold once. If one bundle
fails, previous successful bundle records remain; the next invocation skips them
and resumes with the failed or still-missing bundle.

Run reusable focused or complete-bundle checks through the controlled runner:

```bash
.venv/bin/python3 scripts/quality/validation/test_bundles.py \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --selectors test/app/features/setup/
.venv/bin/python3 scripts/quality/validation/test_bundles.py \
  --bundle godot
```

If `--selectors` exactly names one registered bundle, it creates the same
coverage-bearing evidence that the full backstop consumes. A narrower node/file result remains
reusable only as that exact focused command and cannot prove its owning bundle.
Raw `pytest` is diagnostic and does not create submission-cache evidence.

The internal `--direct-full` path runs the complete backstop while reusing
valid bundle evidence. `--no-cache` is an explicit clean replay: it must be
passed through the gate and bundle runner, and it must not silently reuse a
focused test, bundle, or backstop record.

The full backstop additionally stores check-scoped evidence for its remaining expensive
backstop. Unknown executable inputs invalidate all bundles. Cache records live under
ignored `build/validation-cache/` and never replace CI for a new commit SHA.

If a selected premerge lane or merge gate fails, do not merge. Unknown,
governance, toolchain and lockfile changes fail closed by selecting every lane.
After main, the complete backstop selects every CI lane rather than rerunning a
serial local-style script: Python bundles and quality, Web, Desktop, Developer
Tools, architecture, persistence, Godot, docs, toolchain, release and runtime
smoke all fan out in parallel. Each main lane uses two non-cancelling parity
slots that retain running work and coalesce obsolete pending tips. A newest-main
red result quarantines ordinary merges until recovery.

### Failure repair ladder

Do not restart a broad gate after every repair edit. Expand only when the prior
level passes or a newly discovered dependency requires it:

1. rerun the exact failed pytest node ID or failing command;
2. if it passes and executable code changed, run its owning test file or module;
3. run the directly affected integration or architecture check only when that
   boundary changed;
4. let the selected exact-SHA CI lane prove the candidate; run full only when
   diagnosing main health or preparing a release.

On the same source state, never repeat a successful command. An environmental
or flaky suspicion permits one diagnostic rerun with the reason recorded; it
does not justify restarting the whole suite. Every expansion must name the new
risk, changed dependency or delivery stage that requires it.

Conformance rows that remain open because the current machine lacks a required
OS or installed host stay explicitly open and must name the missing evidence.
They are not local implementation failures, but they also cannot be presented
as complete; CI or a matching host must provide the missing acceptance before
protected-branch delivery. Focused tests cannot replace a selected lane or the
exact merge gate.

## Documentation verification

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

The pages also need a check of navigation, internal links, mobile layout and
the browser console.
