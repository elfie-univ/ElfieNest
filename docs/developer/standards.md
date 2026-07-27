# Code standards & constraints

This page is the common entry point for every contributor and coding agent. The
goal of the rules is to express boundaries, types and verification directly in
the code, rather than relying on someone's memory.

## Respect the directory boundaries first

- `elfie/` only implements a single complete Elfie; no accounts, Web, Godot
  scenes or desktop lifecycle.
- `nest/` only stores in-nest state and environment; the composition of real
  Elfies and the Nest belongs only in `app/orchestration/`.
- `ai_runtime/` owns models, providers, tools, food and the safety runtime.
- `godot_project/` is the single source of truth for rooms, geometry,
  coordinates, collision and rendering.
- `app/orchestration/lifecycle/` owns Runtime supervision and authority
  lifecycle; `app/interfaces/desktop/` owns the Electron Observer interface and
  public lifecycle client.

When adding a directory or a cross-boundary dependency, you must update the
root README, the architecture docs and the `test/architecture/` contract tests
together.

## Python conventions

- Use the pinned CPython `3.9.25`, `uv.lock`, Ruff and MyPy.
- Types first: public functions, models and events must have explicit types;
  do not use unconstrained `Any` to paper over boundaries.
- Data structures use the Pydantic models in code as the single source of
  truth; do not maintain duplicate JSON Schema docs or export files for
  internal models.
- The test directory mirrors the source directory and uses absolute imports;
  never drop ad-hoc tests at the `test/` root.
- Make small changes, run the tests closest to the change first, then the
  architecture contracts and the quality gate.

## Documentation conventions

- Public design documents are written in English by default, with a Simplified
  Chinese version kept in sync; both describe the final solution, the code
  evidence and how it is verified.
- Intermediate discussion, unimplemented proposals, private worldbuilding and
  experiment records stay outside public documentation and never enter the
  VitePress sidebar.
- A README explains "what it is, how to start, where to go deeper"; do not pass
  process logs off as product documentation.

## Pre-delivery checks

```bash
uv run --no-sync pytest test/architecture/
uv run --no-sync python scripts/check_quality_baseline.py
cd docs && npx --yes pnpm@10.12.1 build
```

Before submitting you must also pass pre-commit and the secret scan; never
bypass checks with `--no-verify`.
