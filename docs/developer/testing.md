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
