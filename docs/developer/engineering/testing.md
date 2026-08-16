# Testing & quality

## Full-suite environment preflight

Before starting the repository-wide pytest gate, check whether the current
host can bind a loopback socket:

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync python scripts/check_quality_environment.py
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
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/<changed-module>/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/architecture/
# Run this only after the preflight above returns 0.
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/
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
uv run --no-sync python scripts/architecture/app_layer_scan.py \
  --project-root . --mode deny-all
uv run --no-sync python scripts/architecture/system_layer_scan.py \
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
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync python scripts/check_quality_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit uv run --no-sync pre-commit run --all-files
```

The quality baseline only admits already-existing diagnostics; any new Ruff,
format or MyPy diagnostic must be fixed — never hidden by widening ignores or
rewriting the baseline.

## Mandatory pre-submit gate

Before committing or pushing, fetch the remote `main` base and run the
CI-aligned hard gate:

```bash
git fetch --prune origin main
bash scripts/pre_submit_gate.sh \
  --base-sha "$(git rev-parse origin/main^{commit})"
```

The gate includes current unstaged changes in a temporary candidate tree and
checks them with immutable-base architecture ratchets. It then runs the lock,
Node/pnpm, quality baseline, pre-commit/Gitleaks, complete pytest, CLI smoke and
documentation build checks. A failed check or a blocked loopback capability
preflight means the change must not be committed, pushed or merged. Focused
tests, deleted tests, broad skips/xfails or a widened quality baseline cannot
replace this gate.

## Documentation verification

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

The pages also need a check of navigation, internal links, mobile layout and
the browser console.
