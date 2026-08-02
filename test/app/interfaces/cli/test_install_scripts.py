from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from test.app.interfaces.cli.installer_test_support import (
    copy_installer_project,
    write_executable,
    write_fake_native_install_tools,
    write_fake_uv,
)
from test.support.paths import PROJECT_ROOT

PINNED_PYTHON_VERSION = "3.9.25"


def test_installer_no_argument_invocation_completes_user_install_in_isolated_home(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    bootstrap_path = project_root / "scripts" / "bootstrap.sh"
    shutil.copy2(PROJECT_ROOT / "scripts" / "bootstrap.sh", bootstrap_path)
    shutil.copy2(
        PROJECT_ROOT / "scripts" / "bootstrap_report.sh",
        project_root / "scripts" / "bootstrap_report.sh",
    )
    shutil.copy2(
        PROJECT_ROOT / "scripts" / "bootstrap_runtime_dependencies.sh",
        project_root / "scripts" / "bootstrap_runtime_dependencies.sh",
    )
    (project_root / "build" / "web").mkdir(parents=True, exist_ok=True)
    (project_root / "build" / "web" / "manifest.json").write_text(
        "{}\n", encoding="utf-8"
    )
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    write_fake_native_install_tools(fake_bin)
    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_UV_LOG": str(uv_log),
            "HOME": str(home),
            "PATH": f"{fake_bin}:{home / '.local' / 'bin'}:/usr/bin:/bin",
            "ELFIENEST_TEST_APPLICATIONS_ROOT": str(home / "Applications"),
        }
    )

    # When
    result = subprocess.run(
        [str(project_root / "install.sh")],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Installation complete" in result.stdout
    assert (home / ".local" / "bin" / "elfienest").is_file()


def test_installer_env_only_redirects_to_full_user_install(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "PATH": "/usr/bin:/bin",
        }
    )

    # When
    result = subprocess.run(
        ["bash", str(project_root / "install.sh"), "--env-only"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode != 0
    assert "Please run ./install.sh directly" in result.stdout + result.stderr


def test_install_script_delegates_locked_environment_sync_to_bootstrap() -> None:
    # Given
    install_script = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    bootstrap_script = (PROJECT_ROOT / "scripts" / "bootstrap.sh").read_text(
        encoding="utf-8"
    )

    # When
    delegates_build_install = 'bootstrap.sh" ensure --tier=build' in install_script
    uses_locked_uv = (
        '"$uv_bin" sync' in bootstrap_script and "--locked" in bootstrap_script
    )

    # Then
    assert delegates_build_install
    assert uses_locked_uv
    assert ".python-version" in bootstrap_script
    assert "requirements.txt" not in install_script + bootstrap_script
    assert "--source-install-artifact-output" in install_script
    assert "--artifact-output" not in install_script


def test_installer_exposes_elfienest_and_safely_migrates_legacy_wrapper(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)

    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    home_bin = home / "bin"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"

    write_fake_uv(fake_bin)
    write_fake_native_install_tools(fake_bin)
    write_executable(
        home_bin / "elfie",
        f'#!/bin/bash\ncd "{project_root}"\n./elfie.sh "$@"\n',
    )
    write_executable(
        home_bin / "uninstall-elfie",
        (
            "#!/bin/bash\n"
            f'rm -f "{home_bin / "elfie"}"\n'
            f'rm -f "{home_bin / "uninstall-elfie"}"\n'
            'echo "✅ ElfieNest uninstalled"\n'
        ),
    )
    write_executable(local_bin / "elfie", "#!/bin/bash\necho unrelated\n")

    env = os.environ.copy()
    env.update(
        {
            "FAKE_UV_LOG": str(uv_log),
            "HOME": str(home),
            "PATH": f"{fake_bin}:{local_bin}:{home_bin}:/usr/bin:/bin",
            "ELFIENEST_TEST_APPLICATIONS_ROOT": str(home / "Applications"),
        }
    )

    # When
    result = subprocess.run(
        [str(project_root / "install.sh")],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    installed_wrapper = local_bin / "elfienest"
    assert installed_wrapper.is_file()
    assert "managed wrapper v2" in installed_wrapper.read_text(encoding="utf-8")
    assert str(home / "Applications" / "ElfieNest.app") in installed_wrapper.read_text(
        encoding="utf-8"
    )
    assert (local_bin / "uninstall-elfienest").is_file()
    assert not (home_bin / "elfie").exists()
    assert not (home_bin / "uninstall-elfie").exists()
    assert (
        (local_bin / "elfie").read_text(encoding="utf-8").endswith("echo unrelated\n")
    )
    uv_invocations = uv_log.read_text(encoding="utf-8")
    assert f"python install {PINNED_PYTHON_VERSION}" in uv_invocations
    assert "sync --locked" in uv_invocations
    assert PINNED_PYTHON_VERSION in uv_invocations


def test_installer_refuses_to_overwrite_unrelated_elfienest_command(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)

    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    unrelated_wrapper = local_bin / "elfienest"

    write_executable(
        fake_bin / "uv",
        """#!/bin/bash
set -eu
printf '%s\n' "$*" >> "$FAKE_UV_LOG"
mkdir -p .venv/bin
printf '#!/bin/bash\nexit 0\n' > .venv/bin/python3
chmod +x .venv/bin/python3
""",
    )
    write_executable(unrelated_wrapper, "#!/bin/bash\necho unrelated elfienest\n")

    env = os.environ.copy()
    env.update(
        {
            "FAKE_UV_LOG": str(uv_log),
            "HOME": str(home),
            "PATH": f"{fake_bin}:{local_bin}:/usr/bin:/bin",
        }
    )

    # When
    result = subprocess.run(
        [str(project_root / "install.sh")],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode != 0
    assert unrelated_wrapper.read_text(encoding="utf-8").endswith(
        "echo unrelated elfienest\n"
    )
    assert (
        "Command already exists from another project" in result.stdout + result.stderr
    )


def test_elfienest_entrypoint_delegates_development_dependencies_to_bootstrap() -> None:
    # Given
    script = (PROJECT_ROOT / "elfienest.sh").read_text(encoding="utf-8")

    # When
    uses_bootstrap = 'scripts/bootstrap.sh" ensure --tier=dev' in script
    checks_before_ensure = 'scripts/bootstrap.sh" check --tier=dev' in script

    # Then
    assert uses_bootstrap
    assert checks_before_ensure
    assert "missing dependencies" in script.lower()
    assert "--env-only" not in script
    assert "serve)" in script
    assert "serve|server)" not in script
    # Commands include mobile and uninstall in interactive mode
    assert (
        "config|owner|doctor|status|web|desktop|mobile|stop|restart|start|version|v|setup|uninstall)"
        in script
    )
    # Direct command routing delegates to Python CLI, no build-godot-web case
    assert '""|exit|quit|q)' not in script
    assert '"" ) continue ;;' in script


def test_installer_detects_but_does_not_modify_legacy_system_entrypoint() -> None:
    # Given
    script = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    helpers = (PROJECT_ROOT / "scripts" / "elfienest_install_helpers.sh").read_text(
        encoding="utf-8"
    )

    # When
    detects_legacy_system_install = "/usr/local/bin/elfie" in script

    # Then
    assert detects_legacy_system_install
    assert "old system entry" in script + helpers
    assert 'rm -f -- "/usr/local/bin/elfie"' not in script + helpers
    assert "sudo rm -f" in script + helpers
