# ElfieNest tests

> 中文版：[`README_zh.md`](README_zh.md)

`test/` mirrors the source boundaries of the repository. Tests live in the path
that corresponds to the module under test; do not add new `test_*.py` files
directly at the repository root.

## Directory layout

```text
test/
├── app/            # product features, interfaces, infrastructure and cross-module orchestration
├── elfie/          # a single Elfie's profile, brain, nervous system, body, communication and skills
├── nest/           # activity space, state, interaction and Godot interface
├── devtools/       # isolated development tools
├── godot/          # static contracts for Godot scenes and resources
├── infrastructure/ # model, tool, persistence, Godot and platform adapters
├── scripts/        # testable repo-script logic
├── architecture/   # top-level directory, dependency boundary and engineering config contracts
├── e2e/            # cross-module, service or user scenarios
└── support/        # shared test helpers across multiple test domains
```

Module unit tests prove local behavior; `architecture/` prevents directory and
dependency-boundary regressions; `e2e/` validates real composition chains. Do
not replace fast, pinpoint unit tests with end-to-end tests.

## Authoring rules

- For a behavior change, write a failing test first, then the minimal
  implementation;
- Use absolute imports, e.g. `from elfie.brain import ...`;
- Test files are named `test_*.py`, test classes `Test*`, test functions
  `test_*`;
- A new test directory should keep the same responsibility layer as the source;
  add an `__init__.py` when it needs to be imported as a Python package;
- Shared helpers go into the relevant module's `conftest.py` or `test/support/`,
  not into root-level test files;
- Do not depend on external production services, default user directories or
  real keys; use a temporary `ELFIE_HOME` whenever files or databases are
  involved.

## Running

Prepare the locked environment once:

```bash
uv sync --locked --extra dev
```

Run reusable affected tests through the controlled validation runner. A
selector that exactly matches a registered top-level bundle creates the same
coverage-bearing evidence used by the post-submit/release full backstop:

```bash
.venv/bin/python3 scripts/quality/validation/test_bundles.py \
  --base-sha "$(git rev-parse origin/main^{commit})" \
  --selectors test/elfie/brain/
.venv/bin/python3 scripts/quality/validation/test_bundles.py \
  --bundle architecture
```

Direct `pytest` is reserved for diagnosis such as rerunning one failed node. It
does not create reusable submission evidence; after the repair, run the owning
selector or bundle through the controlled runner once.

Full test suite:

```bash
uv run --no-sync python scripts/quality/checks/environment.py
.venv/bin/python3 scripts/quality/validation/test_bundles.py --all
```

Run the preflight first. Exit `2` means the current sandbox cannot bind the
loopback port used by the gateway tests; run the full command once in an
environment that permits the bind instead of running the suite twice.

Pytest markers currently declared:

- `unit`: local unit tests;
- `integration`: integration tests that combine multiple modules or resources;
- `slow`: slow tests; exclude with `-m "not slow"`.

For example:

```bash
uv run --no-sync pytest -m "not slow" test/
```

Pytest caches, uv caches and coverage reports are local or CI artifacts and
must not be committed as source. For the quality baseline, pre-commit and docs
build — the full contribution gate — see the root `CONTRIBUTING.md`.
