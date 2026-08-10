# Testing & quality

## Test layers

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/<changed-module>/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/
```

The test directory mirrors the source. The root `test/` does not hold test
files directly; the architecture tests guard directory boundaries, legacy
package names, reverse dependencies and engineering-config contracts.

## Architecture-governance checks

```bash
uv run --no-sync python scripts/architecture/app_layer_scan.py \
  --project-root . --baseline test/architecture/baselines/app_layer.py --mode exact
uv run --no-sync python scripts/architecture/system_layer_scan.py \
  --project-root . --baseline test/architecture/baselines/system_layer.py --mode exact
uv run --no-sync pytest test/architecture/
```

The baselines list exact pre-existing violations; they are not allowances for
new code. A migration removes matching entries as it deletes the old call
chain. When a baseline reaches zero it is deleted and the same scanner runs
with `--mode deny-all`. CI also runs the scanner and baseline from the pull
request base commit against candidate production code, so a change cannot
weaken the rule that judges itself. See the
[repository architecture governance contract](./contracts/repository-governance).

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
