from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.features.operations import (
    ActiveSessionResult,
    ActiveSessionsResult,
    ListActiveSessionsQuery,
    OperationsFacade,
)
from app.interfaces.cli import runtime_commands
from infrastructure.persistence.nest_db.store import get_db, hash_password, init_db
from test.app.interfaces.cli.entrypoint_test_support import (
    PROJECT_ROOT,
    write_executable,
)


def test_cli_help_exposes_owner_account_management() -> None:
    python_cli = PROJECT_ROOT / "scripts" / "elfienest.py"
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv" / "bin" / "python3"), str(python_cli), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "owner" in result.stdout
    assert "Owner account menu" in result.stdout


def test_interactive_help_exposes_owner_account_management() -> None:
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
    assert "owner" in result.stdout
    assert "Owner account menu" in result.stdout


def test_owner_menu_reports_current_owner_without_secrets(
    tmp_path: Path,
) -> None:
    elfie_home = tmp_path / ".elfienest"
    db_path = elfie_home / "nest.db"
    init_db(str(db_path))
    password_hash = hash_password("entrypoint-secret")
    with get_db(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, 'owner')",
            ("doctor-bai", password_hash),
        )
        conn.commit()
    env = os.environ.copy()
    env["ELFIE_HOME"] = str(elfie_home)

    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "owner",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        input="1\n0\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "doctor-bai" in result.stdout
    assert "User ID:" in result.stdout
    assert "Login account:" in result.stdout
    assert "Username:" not in result.stdout
    assert "Password status:" in result.stdout
    assert password_hash not in result.stdout
    assert "entrypoint-secret" not in result.stdout


def test_session_cli_prints_account_id_and_token_hash(capsys) -> None:
    class SessionOperations(OperationsFacade):
        def __init__(self) -> None:
            pass

        def list_active_sessions(
            self, query: ListActiveSessionsQuery
        ) -> ActiveSessionsResult:
            assert query.limit == 20
            return ActiveSessionsResult(
                items=(
                    ActiveSessionResult(
                        token_hash="d" * 64,
                        account_id="doctor-bai",
                        expires_at="2099-01-01T00:00:00+00:00",
                    ),
                )
            )

    runtime_commands.show_sessions(SessionOperations())

    output = capsys.readouterr().out
    assert "doctor-bai" in output
    assert "token: dddddddd..." in output


def test_owner_command_rejects_password_argument_without_echoing_it() -> None:
    secret = "must-not-enter-argv"
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "owner",
            "--password",
            secret,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert secret not in result.stderr


def test_owner_menu_has_no_password_positional_interface() -> None:
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "owner",
            "reset-password",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


def test_owner_parser_rejects_unknown_extra_arguments() -> None:
    secret = "unexpected-secret-argument"
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "owner",
            secret,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_config_parser_errors_keep_current_choices() -> None:
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "elfienest.py"),
            "config",
            "invalid-config-path",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "invalid-config-path" in result.stderr
    assert "provider" in result.stderr
    assert "food" in result.stderr


def test_service_entrypoint_rejects_owner_recovery_bypass(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["ELFIE_HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            str(PROJECT_ROOT / "scripts" / "serve.py"),
            "--owner-recovery",
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


def test_interactive_shell_forwards_owner_command(tmp_path: Path) -> None:
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    (project_root / "pyproject.toml").write_text(
        "# marker for runtime mode detection\n"
    )
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")
    (project_root / "scripts").mkdir(parents=True, exist_ok=True)
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
    invocation_log = tmp_path / "owner-invocation.log"
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
        input="owner\nexit\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert invocation_log.read_text(encoding="utf-8").strip() == (
        "scripts/elfienest.py owner"
    )
