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

## Documentation verification

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
```

The pages also need a check of navigation, internal links, mobile layout and
the browser console.
