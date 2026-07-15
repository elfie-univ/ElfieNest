from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from elfienest.persistence.store import get_db, hash_password, init_db
from test.elfienest.cli.entrypoint_test_support import PROJECT_ROOT, write_executable


def test_cli_help_exposes_admin_account_management() -> None:
    python_cli = PROJECT_ROOT / "scripts" / "elfienest.py"
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv" / "bin" / "python3"), str(python_cli), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "admin" in result.stdout
    assert "管理员账号管理" in result.stdout


def test_interactive_help_exposes_admin_account_management() -> None:
    env = os.environ.copy()
    env["TERM"] = "xterm"
    result = subprocess.run(
        [str(PROJECT_ROOT / "elfienest.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        input="help\nexit\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert "admin" in result.stdout
    assert "管理员账号管理" in result.stdout


def test_admin_show_reports_current_administrator_without_secrets(
    tmp_path: Path,
) -> None:
    elfie_home = tmp_path / ".elfienest"
    db_path = elfie_home / "nest.db"
    init_db(str(db_path))
    password_hash = hash_password("entrypoint-secret")
    with get_db(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            ("doctor-bai", password_hash),
        )
        conn.commit()
    env = os.environ.copy()
    env["ELFIE_HOME"] = str(elfie_home)

    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "admin",
            "show",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "doctor-bai" in result.stdout
    assert str(db_path) in result.stdout
    assert password_hash not in result.stdout
    assert "entrypoint-secret" not in result.stdout


def test_admin_help_exposes_show_and_reset_without_password_argument() -> None:
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "admin",
            "--help",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "show" in result.stdout
    assert "reset-password" in result.stdout
    assert "--password" not in result.stdout


def test_admin_reset_help_accepts_only_optional_username() -> None:
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "admin",
            "reset-password",
            "--help",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "username" in result.stdout
    assert "--password" not in result.stdout


def test_admin_reset_rejects_password_as_extra_positional_argument() -> None:
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "admin",
            "reset-password",
            "doctor-bai",
            "must-not-enter-argv",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "must-not-enter-argv" not in result.stdout
    assert "must-not-enter-argv" not in result.stderr


def test_non_admin_parser_errors_keep_existing_diagnostics() -> None:
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "models",
            "invalid-model-command",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "invalid-model-command" in result.stderr
    assert "list" in result.stderr
    assert "scan" in result.stderr


def test_service_entrypoint_rejects_admin_recovery_bypass(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["ELFIE_HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "serve.py"),
            "--admin-recovery",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_interactive_shell_forwards_admin_reset_username(tmp_path: Path) -> None:
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")
    invocation_log = tmp_path / "admin-invocation.log"
    write_executable(
        project_root / ".venv" / "bin" / "python3",
        """#!/bin/bash
if [ "${1:-}" = "-c" ]; then
    exit 0
fi
printf '%s\n' "$*" > "$ENTRYPOINT_LOG"
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(invocation_log),
            "TERM": "xterm",
        }
    )

    result = subprocess.run(
        [str(project_root / "elfienest.sh")],
        cwd=project_root,
        env=env,
        input="admin reset-password doctor-bai\nexit\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert invocation_log.read_text(encoding="utf-8").strip() == (
        "scripts/elfienest.py admin reset-password doctor-bai"
    )
