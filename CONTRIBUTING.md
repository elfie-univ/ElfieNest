# Contributing to ElfieNest

> 中文版：[`CONTRIBUTING_zh.md`](CONTRIBUTING_zh.md)

Thanks for wanting to improve ElfieNest. This repository holds the Python Core,
the Electron desktop host, the Godot source project and the public docs site at
the same time. Before writing any code, confirm which boundary your change
belongs to.

## Before you start

1. Read the root `AGENTS.md` for the mandatory architecture, safety and
   operation rules.
2. Read the relevant module's `README.md`; the public architecture reference
   lives under `docs/developer/`.
3. Search existing issues first to make sure the problem has not already been
   reported.
4. For any behavior change, add a failing test first, then make the minimal
   implementation.

## Development environment

ElfieNest manages all dependencies through `scripts/bootstrap.sh`, in two
tiers:

- **dev (contributors)**: Python dev + frontend + Godot editor/Web export + Electron dev deps
- **build (source/package build)**: the release toolchain for the current native target

### Quick start

```bash
./elfienest.sh              # auto-detect and install dependencies, then open the interactive menu
```

The first source-development run installs required development dependencies.
Public Ollama remains optional and is selected explicitly in Setup.

### Manual dependency management

```bash
# Check dependency status
./scripts/bootstrap.sh check --tier=dev

# Ensure missing dependencies are installed
./scripts/bootstrap.sh ensure --tier=dev
```

Bootstrap resolves the repository-pinned pnpm release from each package
directory. If no compatible pnpm command is available, it runs the exact
pinned release through `npx`; it never installs or overwrites a global pnpm.

The private root `package.json` anchors the shared Node.js 20+ and pnpm
10.12.1 toolchain without owning application dependencies. The Web frontend,
desktop host, docs site and Developer Tools keep separate manifests and
lockfiles. Verify that their declarations stay aligned with:

```bash
bash scripts/check_node_toolchain.sh
```

### Python environment contract
The 3.9.25 contract in `requires-python`, lockfile, CI and launch scripts. All
install, dev, test, code review and script runs go through `scripts/bootstrap.sh`
and the repository's `.venv/bin/python3`; do not call system
`python` / `python3`, reuse other virtual environments, or set an
`ELFIENEST_PYTHON` override entry.

### Frontend development

The frontend uses Node.js 20+ and pnpm:

```bash
cd app/interfaces/web/frontend
pnpm install --frozen-lockfile
pnpm build       # build into build/web/
pnpm test        # run frontend tests
```

### Docs site

The docs site uses Node.js 20 and pnpm 10.12.1:

```bash
cd docs
pnpm install --frozen-lockfile
pnpm build
```

Do not hand-edit lockfiles. Only update the relevant lockfile when a dependency
has actually changed, and explain why in the PR.

## Pick the right directory

- `elfie/`: a single complete creature's profile, brain, nervous system, body,
  communication and skills.
- `nest/`: activity space, in-nest state, environment time and interaction
  propagation; must not hold real Elfie objects.
- `app/orchestration/`: cross-module flows that compose real `Elfie`, `Nest`
  and `ai_runtime`.
- `app/features/`: product use-cases; `app/interfaces/`: API, Web, CLI;
  `app/infrastructure/`: persistence, filesystem, audio and device
  capabilities.
- `ai_runtime/`: models, providers, routing, tools, safety and the inference
  runtime.
- `app/interfaces/desktop/`: visible Electron windows, platform adaptation and
  the public Runtime lifecycle client; it does not own Runtime processes.
- `godot_project/`: standalone Godot source project; the single source project
  for houses, geometry, coordinates, collision, motion and rendering.
- `devtools/`: module workbenches isolated from the end-user product.
- `docs/`: the only content that goes into the public documentation site.
- `test/`: tests mirroring the source structure; never add `test_*.py` directly
  at the root.

Before adding a top-level directory or a cross-boundary dependency, you must
update the architecture contract tests, the relevant READMEs and the Developer
docs in lockstep.

## Code standards

### Python

- Use Python 3.9-compatible syntax and types; use explicit types at stable
  module boundaries and do not pass around bare dicts.
- New or modified functions must have accurate types; do not use `Any` to paper
  over an unclear model.
- At data entry points, parse into Pydantic v2 models first; Pydantic models in
  code are the single source of truth for internal contracts.
- Errors must carry actionable context; never swallow exceptions or just print
  and continue.
- A single Python file is capped at 250 lines of pure source; split by
  responsibility when exceeded.
- Tests use absolute imports and live in the `test/<module>/` path matching the
  source.

The repository carries a machine-readable historical quality-debt baseline at
`.quality-baseline.json`. It is not an exemption list: existing diagnostics can
be gradually eliminated, but any new Ruff, Ruff format or MyPy diagnostic fails
the check. Do not use `--write-baseline` to absorb your own new issues; only a
dedicated quality-debt change may update the baseline.

### TypeScript

- Keep `strict` type checking; do not use unjustified `any` or non-null
  assertions.
- Electron only owns the desktop lifecycle and platform boundary; it carries no
  product business rules.
- After changing `app/interfaces/desktop/`, run its existing tests and
  TypeScript checks and list the commands in the PR.

### GDScript

- Godot is only responsible for scenes, geometry, coordinates, collision,
  motion and rendering.
- Before opening, running or screenshotting Godot, follow
  `.agents/skills/godot-project-operator/SKILL.md` to check the version and
  existing processes.
- Do not commit `.godot/`, import caches or unrelated editor-generated changes.

## Tests and quality gate

Run at least the following before submitting:

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync pytest test/architecture/
UV_CACHE_DIR=/tmp/elfienest-uv-cache uv run --no-sync python scripts/check_quality_baseline.py
PRE_COMMIT_HOME=/tmp/elfienest-precommit uv run --no-sync pre-commit run --all-files
```

Then run the unit, integration or end-to-end tests directly related to your
change. For docs changes also run:

```bash
cd docs
npx --yes pnpm@10.12.1 build
```

Never use `--no-verify`, and never hide failures with broad ignores, deleted
tests or an updated quality baseline.

## Docs and public content

- The default language for public documents is **English**; a Simplified
  Chinese version is maintained in lockstep.
- README-class files use the `README.md` (English, default) + `README_zh.md`
  (Chinese) pair; root-level community docs use the same `_zh.md` suffix
  convention (e.g. `CONTRIBUTING.md` / `CONTRIBUTING_zh.md`).
- The `docs/` VitePress site uses the `locales` mechanism: English is the site
  root, Chinese lives under `docs/zh/`.
- **Any content change to a public document (README, community doc, or docs
  site page) must be applied to both the English and Chinese versions in the
  same change.** Updating only one side is treated as incomplete.
- `docs/` only contains finalized content that the end reader needs; it does
  not store meeting notes, prompts, model intermediate drafts or historical
  proposals.
- `.omo/` and `.agents/knowledge/` are local private areas; never link, excerpt
  or copy them into public docs.
- Capability claims must be provable by the current code, tests or a replayable
  scenario; unreleased capabilities must be explicitly marked as planned or
  kept private.
- When changing behavior, commands, directory boundaries or configuration,
  update the corresponding README and Developer docs in lockstep.

## Branch and commit scope

- One PR solves one well-scoped problem; avoid drive-by formatting or
  refactoring of unrelated files.
- Do not overwrite others' uncommitted changes; do not commit local configs,
  generated artifacts, caches or production data.
- Commit messages explain "why", not just list filenames.
- UI or docs-site changes must be visually accepted by the maintainer first;
  keep changes local, uncommitted and unpushed until accepted.

## A Pull Request must include

- The problem and scope, plus what is explicitly out of scope for this PR.
- Affected modules and architecture boundaries.
- The actual test commands you ran and their results.
- Whether README, Developer docs and user docs need a sync update, and whether
  the English/Chinese pair was kept in sync.
- Whether the change involves config migration, user data, security boundaries
  or public capability claims.
- Screenshots or reproducible acceptance steps for UI changes.

## Prohibited

- Committing API keys, tokens, passwords, private addresses, user data or
  unredacted logs.
- Restoring the legacy top-level packages `runtime/` or `elfienest/`.
- Holding or creating real Elfies inside `nest/`, or copying Godot scene /
  geometry facts into Python.
- Bypassing product and security boundaries inside `app/interfaces/desktop/`,
  Godot or the debug platform.
- Publishing private worldbuilding, partnership material, unreleased
  capabilities or model-generated intermediate designs.
- Bypassing pre-commit, Gitleaks, architecture tests or the user review gate.

Submitting a contribution means you agree to abide by `CODE_OF_CONDUCT.md` and
to provide your contribution under the Apache License 2.0.
