# Build & release

## Build directories

```text
build/  reproducible intermediate build artifacts, not committed
dist/   final release artifacts, not committed
docs/.vitepress/dist/  VitePress build output, not committed
```

Generated Godot Web, Desktop JavaScript and Python Core must go into the
corresponding build directory; they are never written back into source
directories.

## Docs site

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
DOCS_BASE=/ npx --yes pnpm@10.12.1 build
```

GitHub Pages uses the `/ElfieNest/` base. Pull Requests only build; only commits
that have been reviewed by the maintainer and merged into `main` may enter the
Pages deploy job.

## Release gate

Before releasing you must confirm:

1. Code, tests and documentation facts agree;
2. Gitleaks, the quality baseline and architecture tests pass;
3. No private worldbuilding, partnership material or unreviewed screenshots are
   on the public pages;
4. The user has completed visual acceptance of the pages;
5. The maintainer then decides when to commit, push and deploy.

## 0.1.0 internal-test desktop installer

We currently build only internal-test installers: the version is pinned to
`0.1.0`, with no auto-update configured, no public Release upload, and no model
weights packaged. Each platform must be built on its corresponding native
runner: macOS ARM64, macOS x64, Windows x64, Linux x64. The Python Core cannot
be cross-faked; the Ollama model is written to `${ELFIE_HOME}/models/` only on
first use.

The build sequence is below; all intermediates live in `build/`, and the final
installer only in `dist/`:

```bash
# 1. Product frontend
cd app/interfaces/web/frontend
npx --yes pnpm@10.12.1 install --frozen-lockfile
npx --yes pnpm@10.12.1 build
cd ../../../..

# 2. Freeze the Python Core for the current target platform
uv sync --locked --extra release
.venv/bin/python scripts/package_python_core.py freeze-core \
  --target darwin-arm64 --output-dir build/python-core/darwin-arm64

# 3. Export Godot Web (using the project-required Godot 4.7 and Web Export Templates)
python3 scripts/build_godot_web.py

# 4. After downloading the Ollama archive whose version and SHA-256 match the manifest, assemble single-target staging
.venv/bin/python scripts/assemble_desktop_resources.py \
  --target darwin-arm64 \
  --ollama-archive build/downloads/ollama/darwin-arm64/ollama-darwin.tgz

# 5. Build only the unsigned internal installer for the current target
cd desktop
ELFIENEST_TARGET=darwin-arm64 \
  npx --yes pnpm@10.12.1 exec electron-builder --mac --arm64 --publish never
```

The first internal-test macOS and Windows installers are neither signed nor
notarized, so the system shows an origin warning; this is a current
internal-test constraint and must not be bypassed by disabling security
mechanisms. Install tests must record four results — install, launch,
`/api/health` success, and no child processes after exit — before being handed
to the next tester.
