from __future__ import annotations

import os
import subprocess
from pathlib import Path

from test.elfienest.cli.installer_test_support import (
    copy_installer_project,
    write_executable,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PINNED_PYTHON_VERSION = "3.9.25"


def test_install_script_syncs_locked_uv_environment() -> None:
    # Given
    script = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    # When
    uses_locked_uv = '"$uv_bin" sync' in script and "--locked" in script

    # Then
    assert uses_locked_uv
    assert ".python-version" in script
    assert "requirements.txt" not in script
    assert "ELFIENEST_PYTHON" in script


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

    write_executable(
        fake_bin / "uv",
        """#!/bin/bash
set -eu
printf '%s\n' "$*" >> "$FAKE_UV_LOG"
mkdir -p .venv/bin
cat > .venv/bin/python3 <<'PYTHON'
#!/bin/bash
exit 0
PYTHON
chmod +x .venv/bin/python3
""",
    )
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
            'echo "✅ ElfieNest 已卸载"\n'
        ),
    )
    write_executable(local_bin / "elfie", "#!/bin/bash\necho unrelated\n")

    env = os.environ.copy()
    env.update(
        {
            "FAKE_UV_LOG": str(uv_log),
            "HOME": str(home),
            "PATH": f"{fake_bin}:{local_bin}:{home_bin}:/usr/bin:/bin",
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
    assert 'exec "$PROJECT_ROOT/elfienest.sh" "$@"' in installed_wrapper.read_text(
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
    assert "不属于当前项目" in result.stdout + result.stderr


def test_elfienest_entrypoint_can_self_repair_missing_runtime_dependencies() -> None:
    # Given
    script = (PROJECT_ROOT / "elfienest.sh").read_text(encoding="utf-8")

    # When
    has_repair_path = "repair_project_venv" in script

    # Then
    assert has_repair_path
    assert "ELFIENEST_SKIP_AUTO_REPAIR" in script
    assert "install.sh" in script
    assert "--env-only" in script
    assert ".python-version" in script
    assert 'start|serve)' in script
    assert 'build-godot-web)' in script


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
    assert "旧版系统入口" in script + helpers
    assert 'rm -f -- "/usr/local/bin/elfie"' not in script + helpers
    assert "sudo rm -f" in script + helpers
