from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from test.scripts.bootstrap_test_support import (
    copy_bootstrap,
    make_executable,
    prepare_build_runtime,
)
from test.support.paths import PROJECT_ROOT


def _prepare_dev_project(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    make_executable(project_root / ".venv/bin/pre-commit")
    make_executable(project_root / ".venv/bin/ruff")
    desktop_dir = project_root / "app/interfaces/desktop"
    desktop_dir.mkdir(parents=True)
    (desktop_dir / "package.json").write_text(
        '{"packageManager":"pnpm@10.12.1"}\n',
        encoding="utf-8",
    )
    host_main = project_root / "app/bootstrap/desktop_host/host_main.mjs"
    host_main.parent.mkdir(parents=True)
    host_main.write_text("host\n", encoding="utf-8")
    authority_main = (
        project_root / "infrastructure/godot/lifecycle/electron/authority_main.mjs"
    )
    authority_main.parent.mkdir(parents=True)
    authority_main.write_text("authority\n", encoding="utf-8")
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()
    fake_bin = project_root / ".fake-bin"
    make_executable(fake_bin / "node", "#!/bin/sh\nprintf 'v22.22.3\\n'\n")
    return project_root, scripts_dir, elfie_home, fake_bin


def test_dev_bootstrap_uses_package_pnpm_when_root_corepack_version_differs(
    tmp_path: Path,
) -> None:
    # Given: Corepack selects a default pnpm at the root and the pinned pnpm in package.
    project_root, scripts_dir, elfie_home, fake_bin = _prepare_dev_project(tmp_path)
    global_install_marker = tmp_path / "global-install-called"
    make_executable(
        fake_bin / "pnpm",
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        '  case "$PWD" in\n'
        '    */app/interfaces/desktop) printf "10.12.1\\n" ;;\n'
        '    *) printf "11.5.2\\n" ;;\n'
        "  esac\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "install" ]; then\n'
        "  mkdir -p node_modules/.bin\n"
        "  printf '#!/bin/sh\\nexit 0\\n' > node_modules/.bin/electron\n"
        "  chmod +x node_modules/.bin/electron\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "rebuild" ] && [ "$2" = "electron" ]; then exit 0; fi\n'
        'if [ "$1" = "build" ]; then\n'
        "  mkdir -p ../../../build/components/desktop-interface\n"
        "  printf 'built\\n' > ../../../build/components/desktop-interface/main.js\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
    )
    make_executable(
        fake_bin / "npm",
        '#!/bin/sh\nprintf "called\\n" > "$GLOBAL_INSTALL_MARKER"\nexit 91\n',
    )

    # When: a new worktree prepares its missing Electron authority host.
    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "ensure", "--tier=dev"],
        cwd=project_root,
        env={
            **os.environ,
            "ELFIE_HOME": str(elfie_home),
            "GLOBAL_INSTALL_MARKER": str(global_install_marker),
            "HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: package-local resolution succeeds without changing global npm state.
    assert result.returncode == 0, result.stderr
    assert not global_install_marker.exists()
    assert "pnpm 10.12.1 ready" in result.stdout


def test_dev_bootstrap_uses_pinned_npx_when_pnpm_is_absent(tmp_path: Path) -> None:
    # Given: Node and npx exist, but no global or Corepack pnpm command is available.
    project_root, scripts_dir, elfie_home, fake_bin = _prepare_dev_project(tmp_path)
    global_install_marker = tmp_path / "global-install-called"
    npx_calls = tmp_path / "npx-calls"
    make_executable(
        fake_bin / "npm",
        '#!/bin/sh\nprintf "called\\n" > "$GLOBAL_INSTALL_MARKER"\nexit 91\n',
    )
    make_executable(
        fake_bin / "npx",
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$NPX_CALLS"\n'
        'if [ "$1" != "--yes" ] || [ "$2" != "pnpm@10.12.1" ]; then exit 92; fi\n'
        "shift 2\n"
        'if [ "$1" = "--version" ]; then printf "10.12.1\\n"; exit 0; fi\n'
        'if [ "$1" = "install" ]; then\n'
        "  mkdir -p node_modules/.bin\n"
        "  printf '#!/bin/sh\\nexit 0\\n' > node_modules/.bin/electron\n"
        "  chmod +x node_modules/.bin/electron\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "rebuild" ] && [ "$2" = "electron" ]; then exit 0; fi\n'
        'if [ "$1" = "build" ]; then\n'
        "  mkdir -p ../../../build/components/desktop-interface\n"
        "  printf 'built\\n' > ../../../build/components/desktop-interface/main.js\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
    )

    # When: bootstrap prepares a fresh worktree without a pnpm executable.
    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "ensure", "--tier=dev"],
        cwd=project_root,
        env={
            **os.environ,
            "ELFIE_HOME": str(elfie_home),
            "GLOBAL_INSTALL_MARKER": str(global_install_marker),
            "HOME": str(tmp_path / "home"),
            "NPX_CALLS": str(npx_calls),
            "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: every pnpm operation uses the pinned ephemeral package and never npm -g.
    assert result.returncode == 0, result.stderr
    assert not global_install_marker.exists()
    assert npx_calls.read_text(encoding="utf-8").splitlines() == [
        "--yes pnpm@10.12.1 --version",
        "--yes pnpm@10.12.1 install --frozen-lockfile",
        "--yes pnpm@10.12.1 rebuild electron",
        "--yes pnpm@10.12.1 build",
    ]


def test_desktop_manifest_allows_the_electron_install_script() -> None:
    # Given: pnpm 10 blocks dependency build scripts unless the package opts in.
    manifest = json.loads(
        (PROJECT_ROOT / "app/interfaces/desktop/package.json").read_text(
            encoding="utf-8"
        )
    )

    # When: the desktop dependency policy is inspected.
    pnpm_policy = manifest.get("pnpm", {})

    # Then: Electron's postinstall download is explicitly allowed.
    assert pnpm_policy.get("onlyBuiltDependencies") == ["electron"]


def test_dev_bootstrap_fails_when_electron_is_still_missing_after_install(
    tmp_path: Path,
) -> None:
    # Given: pnpm commands report success but never create an Electron executable.
    project_root, scripts_dir, elfie_home, fake_bin = _prepare_dev_project(tmp_path)
    make_executable(
        fake_bin / "pnpm",
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then printf "10.12.1\\n"; exit 0; fi\n'
        'if [ "$1" = "build" ]; then\n'
        "  mkdir -p ../../../build/components/desktop-interface\n"
        "  printf 'built\\n' > ../../../build/components/desktop-interface/main.js\n"
        "fi\n"
        "exit 0\n",
    )

    # When: bootstrap attempts to prepare the missing authority host.
    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "ensure", "--tier=dev"],
        cwd=project_root,
        env={
            **os.environ,
            "ELFIE_HOME": str(elfie_home),
            "HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: it reports the real missing runtime instead of claiming success.
    assert result.returncode == 1
    assert "Electron authority host is still unavailable" in result.stderr
