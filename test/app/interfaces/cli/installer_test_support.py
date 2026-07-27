from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from test.support.paths import PROJECT_ROOT


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def copy_installer_project(destination: Path) -> None:
    destination.mkdir(parents=True)
    relative_paths = (
        Path("install.sh"),
        Path("elfienest.sh"),
        Path(".python-version"),
        Path("uv.lock"),
        Path("scripts/bootstrap.sh"),
        Path("scripts/bootstrap_report.sh"),
        Path("scripts/bootstrap_runtime_dependencies.sh"),
        Path("scripts/elfienest_install_helpers.sh"),
        Path("scripts/native_install_artifact.sh"),
        Path("scripts/release.py"),
    )
    for relative_path in relative_paths:
        source = PROJECT_ROOT / relative_path
        if not source.exists():
            continue
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (destination / "build/web").mkdir(parents=True, exist_ok=True)
    (destination / "build/web/manifest.json").write_text("{}\n", encoding="utf-8")
    godot_web = destination / "build/components/godot-web"
    for suffix in ("html", "js", "wasm", "pck"):
        (godot_web / f"elfienest.{suffix}").parent.mkdir(parents=True, exist_ok=True)
        (godot_web / f"elfienest.{suffix}").write_text("runtime\n", encoding="utf-8")
    fake_dmg = destination / "build" / "ElfieNest-test.dmg"
    fake_dmg.write_bytes(b"not-a-real-dmg")
    packaged_cli = (
        destination
        / "build"
        / "fake-dmg"
        / "ElfieNest.app"
        / "Contents"
        / "Resources"
        / "management-cli"
        / "ElfieNestCli"
    )
    packaged_cli.parent.mkdir(parents=True, exist_ok=True)
    packaged_cli.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    packaged_cli.chmod(0o755)
    (
        destination
        / "build"
        / "fake-dmg"
        / "ElfieNest.app"
        / "Contents"
        / "Resources"
        / "manifest.json"
    ).write_text('{"version":"0.1.0"}\n', encoding="utf-8")


def write_fake_uv(fake_bin: Path) -> Path:
    uv_path = fake_bin / "uv"
    write_executable(
        uv_path,
        """#!/bin/bash
set -eu
printf '%s\n' "$*" >> "$FAKE_UV_LOG"
if [ "${1:-}" = "--version" ]; then
    echo "uv 0.9.26"
    exit 0
fi
if [ "${1:-}" = "python" ] && [ "${2:-}" = "install" ]; then
    [ "${FAKE_UV_FAIL_PYTHON_INSTALL:-0}" != "1" ] || exit 41
    exit 0
fi
if [ "${1:-}" = "sync" ]; then
    [ "${FAKE_UV_FAIL_SYNC:-0}" != "1" ] || exit 42
    venv_dir="${UV_PROJECT_ENVIRONMENT:-.venv}"
    mkdir -p "$venv_dir/bin"
    cat > "$venv_dir/bin/python3" <<'PYTHON'
#!/bin/bash
if [[ "${1:-}" = */scripts/release.py ]]; then
    while [ "$#" -gt 0 ]; do
        if [ "$1" = "--artifact-output" ] || [ "$1" = "--source-install-artifact-output" ]; then
            printf '%s\n' "$(pwd)/build/ElfieNest-test.dmg" > "$2"
            exit 0
        fi
        shift
    done
fi
exit 0
PYTHON
    chmod +x "$venv_dir/bin/python3"
    cp "$venv_dir/bin/python3" "$venv_dir/bin/python"
    chmod +x "$venv_dir/bin/python"
    exit 0
fi
exit 0
""",
    )
    return uv_path


def write_fake_native_install_tools(fake_bin: Path) -> None:
    write_executable(
        fake_bin / "uname",
        """#!/bin/bash
if [ "${1:-}" = "-s" ]; then echo Darwin; else echo x86_64; fi
""",
    )
    write_executable(
        fake_bin / "hdiutil",
        """#!/bin/bash
set -eu
if [ "$1" = "attach" ]; then
    while [ "$#" -gt 0 ]; do
        if [ "$1" = "-mountpoint" ]; then
            cp -R "$(pwd)/build/fake-dmg/ElfieNest.app" "$2/ElfieNest.app"
            exit 0
        fi
        shift
    done
fi
exit 0
""",
    )


def installer_environment(
    home: Path,
    fake_bin: Path,
    uv_log: Path,
    *,
    path: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_UV_LOG": str(uv_log),
            "HOME": str(home),
            "PATH": path
            or f"{fake_bin}:{home / '.local' / 'bin'}:{home / 'bin'}:/usr/bin:/bin",
            "SHELL": "/bin/bash",
            "ELFIENEST_TEST_APPLICATIONS_ROOT": str(home / "Applications"),
        }
    )
    if extra is not None:
        environment.update(extra)
    write_fake_native_install_tools(fake_bin)
    return environment


def run_installer(
    project_root: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(project_root / "install.sh")],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
