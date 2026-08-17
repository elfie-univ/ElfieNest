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

## Tiered validation gate

Fetch the remote `main` base, then run the smallest safe tier:

```bash
git fetch --prune origin main
bash scripts/pre_submit_gate.sh --stage commit \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --closure-file task-closure.json
# feature push: use --stage push
# main merge or release: use --stage main
```

G1 (`commit`) checks changed files, affected tests and closure `progress`. G2
(`push`) adds the quality baseline and affected API, persistence, architecture
or documentation integration checks. G3 (`main`) runs the complete gate below,
including immutable-base architecture ratchets, lock and toolchain checks,
pre-commit/Gitleaks, complete pytest, CLI smoke and documentation build. Unknown
executable, governance, toolchain and lockfile changes escalate to G3. A
successful exact-candidate result may be reused from ignored
`build/validation-cache/`; it never replaces CI for a new commit SHA.

If a required check fails or the G3 loopback preflight is blocked, do not commit,
push or merge. Focused tests are the normal G1/G2 path; they do not replace G3
when the impact classifier requires it.

The closure check rejects unclassified changes, incomplete evidence rows, and
listed Conformance rows that are not closed. If a row is blocked only because
the current machine lacks a required OS or installed host, classify it as
`blocker_class: "external_environment"` and use the explicit local checkpoint
flag:

```bash
bash scripts/pre_submit_gate.sh \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --closure-file task-closure.json \
  --allow-external-environment-blockers
```

This exception does not close the row, does not allow code or tool failures,
and must not be used for final protected-branch delivery; CI or a matching host
still has to run the missing acceptance. Focused tests cannot replace either
gate.

Changes to the closure skill or gate itself use two checkpoints: land the
governance-only classifier registration first, then land the protected checker
and integration. The immutable-base guard must not be bypassed to combine them.

## Documentation verification

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

The pages also need a check of navigation, internal links, mobile layout and
the browser console.
