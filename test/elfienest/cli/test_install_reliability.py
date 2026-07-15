from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from test.elfienest.cli.installer_test_support import (
    PROJECT_ROOT,
    copy_installer_project,
    installer_environment,
    run_installer,
    write_executable,
    write_fake_uv,
)


def test_repeat_install_always_runs_locked_sync(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    environment = installer_environment(home, fake_bin, uv_log)
    first_result = run_installer(project_root, environment)
    assert first_result.returncode == 0, first_result.stdout + first_result.stderr

    # When
    second_result = run_installer(project_root, environment)

    # Then
    assert second_result.returncode == 0, second_result.stdout + second_result.stderr
    sync_invocations = [
        line
        for line in uv_log.read_text(encoding="utf-8").splitlines()
        if line.startswith("sync ")
    ]
    assert len(sync_invocations) == 2
    assert all("--locked" in invocation for invocation in sync_invocations)


def test_failed_repeat_sync_preserves_installed_commands(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    environment = installer_environment(home, fake_bin, uv_log)
    first_result = run_installer(project_root, environment)
    assert first_result.returncode == 0, first_result.stdout + first_result.stderr
    wrapper = home / ".local" / "bin" / "elfienest"
    uninstaller = home / ".local" / "bin" / "uninstall-elfienest"
    original_wrapper = wrapper.read_bytes()
    original_uninstaller = uninstaller.read_bytes()
    environment["FAKE_UV_FAIL_SYNC"] = "1"

    # When
    failed_result = run_installer(project_root, environment)

    # Then
    assert failed_result.returncode != 0
    assert wrapper.read_bytes() == original_wrapper
    assert uninstaller.read_bytes() == original_uninstaller


def test_failed_python_install_preserves_installed_commands(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    environment = installer_environment(home, fake_bin, uv_log)
    first_result = run_installer(project_root, environment)
    assert first_result.returncode == 0, first_result.stdout + first_result.stderr
    wrapper = home / ".local" / "bin" / "elfienest"
    uninstaller = home / ".local" / "bin" / "uninstall-elfienest"
    original_wrapper = wrapper.read_bytes()
    original_uninstaller = uninstaller.read_bytes()
    environment["FAKE_UV_FAIL_PYTHON_INSTALL"] = "1"

    # When
    failed_result = run_installer(project_root, environment)

    # Then
    assert failed_result.returncode != 0
    assert wrapper.read_bytes() == original_wrapper
    assert uninstaller.read_bytes() == original_uninstaller


def test_custom_python_skips_managed_python_download(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    custom_python = tmp_path / "custom python"
    write_executable(custom_python, "#!/bin/bash\nexit 0\n")
    environment = installer_environment(
        home,
        fake_bin,
        uv_log,
        extra={"ELFIENEST_PYTHON": str(custom_python)},
    )

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    uv_invocations = uv_log.read_text(encoding="utf-8").splitlines()
    assert not any(line.startswith("python install ") for line in uv_invocations)
    assert any(str(custom_python) in line for line in uv_invocations)


def test_installer_uses_first_eligible_home_directory_on_path(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    home_bin = home / "bin"
    local_bin = home / ".local" / "bin"
    home_bin.mkdir(parents=True)
    local_bin.mkdir(parents=True)
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    path = f"{fake_bin}:{home_bin}:{local_bin}:/usr/bin:/bin"
    environment = installer_environment(home, fake_bin, uv_log, path=path)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert (home_bin / "elfienest").is_file()
    assert not (local_bin / "elfienest").exists()


def test_installer_ignores_unmanaged_home_path_directories(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    managed_temp_bin = home / ".codex" / "tmp" / "bin"
    home_bin = home / "bin"
    managed_temp_bin.mkdir(parents=True)
    home_bin.mkdir(parents=True)
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    path = f"{managed_temp_bin}:{fake_bin}:{home_bin}:/usr/bin:/bin"
    environment = installer_environment(home, fake_bin, uv_log, path=path)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert (home_bin / "elfienest").is_file()
    assert not (managed_temp_bin / "elfienest").exists()


def test_installer_updates_existing_user_install_after_path_reorder(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    home_bin = home / "bin"
    local_bin = home / ".local" / "bin"
    home_bin.mkdir(parents=True)
    local_bin.mkdir(parents=True)
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    initial_path = f"{fake_bin}:{local_bin}:{home_bin}:/usr/bin:/bin"
    initial_environment = installer_environment(
        home,
        fake_bin,
        uv_log,
        path=initial_path,
    )
    first_result = run_installer(project_root, initial_environment)
    assert first_result.returncode == 0, first_result.stdout + first_result.stderr
    reordered_path = f"{fake_bin}:{home_bin}:{local_bin}:/usr/bin:/bin"
    reordered_environment = installer_environment(
        home,
        fake_bin,
        uv_log,
        path=reordered_path,
    )

    # When
    second_result = run_installer(project_root, reordered_environment)

    # Then
    assert second_result.returncode == 0, second_result.stdout + second_result.stderr
    assert (local_bin / "elfienest").is_file()
    assert not (home_bin / "elfienest").exists()


def test_installer_rejects_earlier_unmanaged_path_command(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    shadow_bin = tmp_path / "shadow-bin"
    shadow_command = shadow_bin / "elfienest"
    write_executable(shadow_command, "#!/bin/bash\nprintf 'shadow\\n'\n")
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    path = f"{shadow_bin}:{fake_bin}:{local_bin}:/usr/bin:/bin"
    environment = installer_environment(home, fake_bin, uv_log, path=path)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode != 0
    assert shadow_command.is_file()
    assert not (local_bin / "elfienest").exists()


def test_installer_rejects_root_before_external_commands_or_output() -> None:
    # Given
    script = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    # When
    root_guard = re.search(
        r"^if \(\( EUID == 0 \)\); then\n(?P<body>.*?)^fi\s*$",
        script,
        flags=re.DOTALL | re.MULTILINE,
    )

    # Then
    assert root_guard is not None
    pre_guard = script[: root_guard.start()]
    assert "$(" not in pre_guard
    assert "dirname" not in pre_guard
    assert "\necho " not in pre_guard
    assert "builtin printf" in root_guard.group("body")
    assert "exit 1" in root_guard.group("body")
    assert (
        "root" in root_guard.group("body").lower()
        or "sudo" in root_guard.group("body").lower()
    )


def test_path_configuration_failure_preserves_commands_and_legacy_install(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    legacy_wrapper = home / "bin" / "elfie"
    legacy_content = f'#!/bin/bash\ncd "{project_root}"\n./elfie.sh "$@"\n'
    write_executable(legacy_wrapper, legacy_content)
    (home / ".bashrc").mkdir(parents=True)
    path = f"{fake_bin}:/usr/bin:/bin"
    environment = installer_environment(home, fake_bin, uv_log, path=path)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode != 0
    assert not (home / ".local" / "bin" / "elfienest").exists()
    assert legacy_wrapper.read_text(encoding="utf-8") == legacy_content
    assert "PATH" in result.stdout + result.stderr


def test_installer_migrates_exact_legacy_wrapper_from_user_path_directory(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    custom_bin = home / ".cargo" / "bin"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    legacy_wrapper = custom_bin / "elfie"
    write_executable(
        legacy_wrapper,
        f'#!/bin/bash\ncd "{project_root}"\n./elfie.sh "$@"\n',
    )
    path = f"{fake_bin}:{custom_bin}:{home / '.local' / 'bin'}:/usr/bin:/bin"
    environment = installer_environment(home, fake_bin, uv_log, path=path)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert not legacy_wrapper.exists()


def test_installer_removes_exact_orphaned_legacy_uninstaller(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    legacy_wrapper = home / "bin" / "elfie"
    legacy_uninstaller = home / "bin" / "uninstall-elfie"
    write_executable(
        legacy_uninstaller,
        (
            "#!/bin/bash\n"
            f'rm -f "{legacy_wrapper}"\n'
            f'rm -f "{legacy_uninstaller}"\n'
            'echo "✅ ElfieNest 已卸载"\n'
        ),
    )
    environment = installer_environment(home, fake_bin, uv_log)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert not legacy_uninstaller.exists()


def test_generated_uninstaller_is_idempotent(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    environment = installer_environment(home, fake_bin, uv_log)
    install_result = run_installer(project_root, environment)
    assert install_result.returncode == 0, install_result.stdout + install_result.stderr
    installed_uninstaller = home / ".local" / "bin" / "uninstall-elfienest"
    saved_uninstaller = tmp_path / "saved-uninstaller"
    shutil.copy2(installed_uninstaller, saved_uninstaller)

    # When
    first = subprocess.run([str(saved_uninstaller)], check=False)
    second = subprocess.run([str(saved_uninstaller)], check=False)

    # Then
    assert first.returncode == 0
    assert second.returncode == 0
    assert not (home / ".local" / "bin" / "elfienest").exists()
    assert not installed_uninstaller.exists()
