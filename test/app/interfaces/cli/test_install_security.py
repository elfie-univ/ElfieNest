from __future__ import annotations

import subprocess
from pathlib import Path

from test.app.interfaces.cli.installer_test_support import (
    copy_installer_project,
    installer_environment,
    run_installer,
    write_executable,
    write_fake_uv,
)


def test_installed_wrapper_treats_hostile_checkout_path_as_data(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / 'Elfie Nest "quoted" $(touch PWNED)'
    copy_installer_project(project_root)
    write_executable(
        project_root / "elfienest.sh",
        "#!/bin/bash\nprintf 'PROJECT:%s\\n' \"$*\"\n",
    )
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    environment = installer_environment(home, fake_bin, uv_log)
    install_result = run_installer(project_root, environment)
    assert install_result.returncode == 0, install_result.stdout + install_result.stderr

    caller = tmp_path / "caller"
    caller.mkdir()
    write_executable(
        caller / "elfienest.sh",
        "#!/bin/bash\nprintf 'CALLER\\n'\n",
    )

    # When
    wrapper_result = subprocess.run(
        [str(home / ".local" / "bin" / "elfienest"), "version"],
        cwd=caller,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert wrapper_result.returncode == 0, wrapper_result.stdout + wrapper_result.stderr
    assert wrapper_result.stdout == "PROJECT:version\n"
    assert not (caller / "PWNED").exists()


def test_installer_preserves_legacy_file_that_only_mentions_project_cd(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    legacy_path = home / "bin" / "elfie"
    legacy_content = (
        f"#!/bin/bash\ncd \"{project_root}\"\nprintf 'this is unrelated\\n'\n"
    )
    write_executable(legacy_path, legacy_content)
    environment = installer_environment(home, fake_bin, uv_log)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert legacy_path.read_text(encoding="utf-8") == legacy_content


def test_installer_preserves_symlinked_legacy_entrypoint(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    legacy_target = tmp_path / "legacy-target"
    write_executable(
        legacy_target,
        f'#!/bin/bash\ncd "{project_root}"\n./elfie.sh "$@"\n',
    )
    legacy_link = home / "bin" / "elfie"
    legacy_link.parent.mkdir(parents=True)
    legacy_link.symlink_to(legacy_target)
    environment = installer_environment(home, fake_bin, uv_log)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert legacy_link.is_symlink()
    assert legacy_target.is_file()


def test_installer_refuses_unrelated_uninstaller(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    uninstaller = home / ".local" / "bin" / "uninstall-elfienest"
    unrelated_content = "#!/bin/bash\nprintf 'unrelated\\n'\n"
    write_executable(uninstaller, unrelated_content)
    environment = installer_environment(home, fake_bin, uv_log)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode != 0
    assert uninstaller.read_text(encoding="utf-8") == unrelated_content


def test_installer_refuses_symlinked_uninstaller(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    uninstaller_target = tmp_path / "unrelated-uninstaller"
    write_executable(uninstaller_target, "#!/bin/bash\nprintf 'unrelated\\n'\n")
    uninstaller_link = home / ".local" / "bin" / "uninstall-elfienest"
    uninstaller_link.parent.mkdir(parents=True)
    uninstaller_link.symlink_to(uninstaller_target)
    environment = installer_environment(home, fake_bin, uv_log)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode != 0
    assert uninstaller_link.is_symlink()
    assert uninstaller_target.is_file()


def test_installer_does_not_follow_predictable_log_symlink(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    temporary_dir = tmp_path / "tmp"
    temporary_dir.mkdir()
    protected_file = tmp_path / "protected"
    protected_file.write_text("keep-me\n", encoding="utf-8")
    (temporary_dir / "elfienest-install.log").symlink_to(protected_file)
    environment = installer_environment(
        home,
        fake_bin,
        uv_log,
        extra={"TMPDIR": str(temporary_dir)},
    )

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert protected_file.read_text(encoding="utf-8") == "keep-me\n"


def test_installer_removes_private_log_on_exit(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    temporary_dir = tmp_path / "tmp"
    temporary_dir.mkdir()
    environment = installer_environment(
        home,
        fake_bin,
        uv_log,
        extra={"TMPDIR": str(temporary_dir)},
    )

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert not tuple(temporary_dir.glob("elfienest-install.*"))


def test_uninstaller_refuses_to_delete_modified_wrapper(tmp_path: Path) -> None:
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
    wrapper = home / ".local" / "bin" / "elfienest"
    uninstaller = home / ".local" / "bin" / "uninstall-elfienest"
    modified_content = (
        "#!/bin/bash\n"
        "# unrelated wrapper\n"
        "PROJECT_ROOT=/tmp/unrelated\n"
        'exec "$PROJECT_ROOT/elfienest.sh" "$@"\n'
    )
    write_executable(wrapper, modified_content)

    # When
    result = subprocess.run(
        [str(uninstaller)],
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode != 0
    assert wrapper.read_text(encoding="utf-8") == modified_content
    assert uninstaller.is_file()


def test_installer_rejects_install_directory_symlink_escaping_home(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    outside_bin = tmp_path / "shared-bin"
    outside_bin.mkdir()
    local_parent = home / ".local"
    local_parent.mkdir(parents=True)
    local_bin = local_parent / "bin"
    local_bin.symlink_to(outside_bin, target_is_directory=True)
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    path = f"{fake_bin}:{local_bin}:/usr/bin:/bin"
    environment = installer_environment(home, fake_bin, uv_log, path=path)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode != 0
    assert not (outside_bin / "elfienest").exists()
    assert not (outside_bin / "uninstall-elfienest").exists()


def test_installer_rejects_group_or_world_writable_install_directory(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    local_bin.chmod(0o777)
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    path = f"{fake_bin}:{local_bin}:/usr/bin:/bin"
    environment = installer_environment(home, fake_bin, uv_log, path=path)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode != 0
    assert not (local_bin / "elfienest").exists()
    assert not (local_bin / "uninstall-elfienest").exists()


def test_installer_rejects_symlink_hiding_unsafe_home_ancestor(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    copy_installer_project(project_root)
    home = tmp_path / "home"
    unsafe_parent = home / "unsafe"
    target = unsafe_parent / "target"
    target_bin = target / "bin"
    target_bin.mkdir(parents=True)
    unsafe_parent.chmod(0o777)
    target.chmod(0o755)
    target_bin.chmod(0o755)
    (home / ".local").symlink_to(target, target_is_directory=True)
    local_bin = home / ".local" / "bin"
    fake_bin = tmp_path / "fake-bin"
    uv_log = tmp_path / "uv.log"
    write_fake_uv(fake_bin)
    path = f"{fake_bin}:{local_bin}:/usr/bin:/bin"
    environment = installer_environment(home, fake_bin, uv_log, path=path)

    # When
    result = run_installer(project_root, environment)

    # Then
    assert result.returncode != 0
    assert not (target_bin / "elfienest").exists()
    assert not (target_bin / "uninstall-elfienest").exists()
