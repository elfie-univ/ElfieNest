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

## 0.1.0-beta.1 internal-test desktop installer

We currently build only internal-test installers: the version is pinned to
`0.1.0-beta.1`, with no auto-update configured and no model weights, Ollama engine or
models packaged. Ollama is an optional public dependency selected during Setup;
an installer never creates a private sidecar.

The coordinator always requests the full four-target matrix: `darwin-arm64`,
`darwin-x64`, `win32-x64`, and `linux-x64`. A matching native runner must build
and install-smoke each target. A missing runner is reported as `incomplete`,
never as a cross-built or passed artifact. All intermediates live in `build/`,
and final installers only in `dist/`.

The native targets are macOS `PKG`, Windows `NSIS`, and Linux `DEB`. Their
installer hooks expose the packaged management CLI as the global `elfienest`
command. POSIX hooks refuse to replace an existing command unless it is the
exact symlink owned by the same package, and removal hooks delete only exact
package-owned launchers. Windows adds and removes only its exact installation
directory from the current user's PATH.

The native runner invokes `scripts/internal/release/release_install_smoke.py` through
`scripts/release.py --run-install-smoke`. The release workflow runs three bounded
cycles. Each cycle installs the package, starts the installed Desktop Controller
through the global launcher, requires `WORLD_READY`, records the Controller,
Core and Godot authority PIDs, stops to `OFFLINE`, proves those recorded PIDs and
the Desktop receipt are gone, and reinstalls the same package as the upgrade
check. The final phase uninstalls the package while proving the selected
`ELFIE_HOME` remains. The resulting JSON contains the reached `WORLD_READY`
state, the Controller PID, the verified stopped PID set, and typed
install/start/health/stop/upgrade/uninstall durations and budgets;
the workflow uploads it beside the installer. A local build without
`--run-install-smoke` does not mutate the host installation.
The smoke runner resolves the Linux package name from the DEB before its initial
cleanup and never performs an unconditional deletion of a global launcher.

```bash
# Build the current native target locally; this does not upload or publish.
.venv/bin/python scripts/release.py --target darwin-x64

# Only on a disposable native release runner; also runs install/upgrade/smoke/uninstall.
.venv/bin/python scripts/release.py --target darwin-x64 --run-install-smoke \
  --smoke-evidence-output dist/ElfieNest-darwin-x64-install-smoke.json

# Ask the coordinator for all targets. Unavailable runners remain incomplete.
.venv/bin/python scripts/release.py
```

The checked-in `.github/workflows/release.yml` is the multi-platform release
pipeline. It uses native GitHub-hosted runners for macOS arm64, macOS Intel,
Windows x64, and Linux x64. A `workflow_dispatch` run builds all four installers
and keeps them as Actions artifacts. Linux runs its real Desktop Controller under
Xvfb and additionally verifies the packaged freedesktop entry. Before any costly
native build, a small preflight binds the project version, existing release tag
and exact `GITHUB_SHA`; a manual publish is rejected unless its tag already
exists at that exact source commit. Pushing a matching tag, for example
`v0.1.0-beta.1`, runs the same matrix, validates the native installer contents,
and publishes the four user-downloadable installers plus `SHA256SUMS` to GitHub
Releases. The typed install-smoke JSON remains in the Actions build artifact
for CI evidence and is not presented as a Release download. Pre-release tags are published with GitHub's
pre-release flag; a manual run only creates a Release when
`publish_release` is enabled and `release_tag` is the matching existing tag at
the workflow source SHA.

For the current version, the normal publication command is:

```bash
git tag -a v0.1.0-beta.1 -m "ElfieNest 0.1.0-beta.1"
git push origin v0.1.0-beta.1
```

The workflow validates the installed resource layout for each package; it does
not sign or notarize the internal-test artifacts. Before handing a package to a
tester, still record the full install, launch, `/api/health`, and clean-exit
evidence described by the release gate above.

Each installer contains Electron, the frontend, Godot Web, the target-native
Python Core and the management CLI. End users install only these platform-native
artifacts; a source checkout remains a development environment.

The first internal-test macOS and Windows installers are neither signed nor
notarized, so the system shows an origin warning. This current constraint must
not be bypassed by disabling security mechanisms. Before handoff, installation
tests must record install, launch, `/api/health` success, and no child process
after exit.

首次内测的 macOS、Windows 安装包没有签名或公证，系统会显示来源警告；这是当前
内测约束，不应通过关闭安全机制来绕过。安装测试必须记录“安装、启动、`/api/health`
成功、退出后子进程不存在”四项结果后，才可交给下一位测试者。
