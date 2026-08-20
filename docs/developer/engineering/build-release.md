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
command and remove only the launcher owned by that installation.

The native runner invokes `scripts/release_install_smoke.py` through
`scripts/release.py --run-install-smoke`. Each bounded cycle installs the
package, starts through the global launcher, waits for `CORE_READY`/`WORLD_READY`,
stops to `OFFLINE`, reinstalls the same package as the upgrade check, and then
uninstalls it while proving the selected `ELFIE_HOME` remains. The resulting JSON
contains typed install/start/health/stop/upgrade/uninstall durations and budgets;
the workflow uploads it beside the installer. A local build without
`--run-install-smoke` does not mutate the host installation.

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
and keeps them as Actions artifacts. Pushing a tag matching the project version,
for example `v0.1.0-beta.1`, runs the same matrix, validates the native installer
contents, publishes each typed install-smoke JSON beside its installer, and
publishes the four installers, `SHA256SUMS`, and a release `manifest.json` to
GitHub Releases. Pre-release tags are published with GitHub's
pre-release flag; a manual run only creates a Release when
`publish_release` is enabled and `release_tag` is set to the matching tag.
The default mode is an unsigned internal preview: tag pushes require no Apple
credentials, macOS artifacts keep `internal` in their filename, and the GitHub
Release is always marked as a Pre-release with an unsigned-macOS warning.

For the current version, the normal publication command is:

```bash
git tag -a v0.1.0-beta.1 -m "ElfieNest 0.1.0-beta.1"
git push origin v0.1.0-beta.1
```

The normal tag command above publishes the unsigned internal preview and does
not read Apple secrets. Local `scripts/release.py` builds use the same unsigned
internal policy. These packages can be installed and tested, but macOS may show
Gatekeeper or verification warnings.

Formal signing is opt-in only. Start the workflow manually, enable
`formal_macos_release`, and provide the matching `release_tag` (plus
`publish_release` when a GitHub Release should be created). Only that explicit
mode requires both Developer ID identities and App Store Connect notarization
credentials; it fails closed and verifies the PKG, Gatekeeper assessment,
stapled ticket, complete app, Python Core, management CLI, and nested Mach-O
signatures.

### macOS signing and notarization credentials

An Apple Developer Program Account Holder creates one **Developer ID
Application** certificate for the app and one **Developer ID Installer**
certificate for the PKG. Apple documents the two distinct certificate purposes
in [Developer ID certificates](https://developer.apple.com/help/account/certificates/create-developer-id-certificates).
Install each certificate with its private key, export each identity as a
separate password-protected PKCS#12 (`.p12`) file, and store only its Base64
contents and password in GitHub Actions secrets.

Create a **team** App Store Connect API key for notarization; an individual key
cannot be used by `notarytool`. The private `.p8` key can be downloaded only
once, so keep it outside the repository. See Apple's
[API key instructions](https://developer.apple.com/documentation/appstoreconnectapi/creating-api-keys-for-app-store-connect-api).

Configure these repository Actions secrets:

| Secret | Value |
| --- | --- |
| `MACOS_APPLICATION_CERTIFICATE` | Base64 of the Developer ID Application `.p12` |
| `MACOS_APPLICATION_CERTIFICATE_PASSWORD` | Password for that `.p12` |
| `MACOS_INSTALLER_CERTIFICATE` | Base64 of the Developer ID Installer `.p12` |
| `MACOS_INSTALLER_CERTIFICATE_PASSWORD` | Password for that `.p12` |
| `APPLE_API_KEY_BASE64` | Base64 of the team `AuthKey_*.p8` file |
| `APPLE_API_KEY_ID` | App Store Connect key ID |
| `APPLE_API_ISSUER` | App Store Connect issuer ID |

The workflow decodes the `.p8` only into the runner's temporary directory. It
maps the two `.p12` secrets to electron-builder's application and installer
certificate inputs, signs with hardened runtime, submits both the app and PKG
through Apple's notary service, and staples the returned tickets. Credential
files and secret values must never be committed.

Each installer contains Electron, the frontend, Godot Web, the target-native
Python Core and the management CLI. End users install only these platform-native
artifacts; a source checkout remains a development environment.

Default GitHub artifacts are internal previews. Their macOS packages are
unsigned and notarization is not claimed; Windows previews may also show a
publisher warning. Missing Apple credentials block only an explicitly selected
formal macOS release. Before handoff, installation tests must record install,
launch, `/api/health` success, and no child process after exit.
