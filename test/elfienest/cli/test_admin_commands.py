from __future__ import annotations

import getpass
from contextlib import nullcontext
from pathlib import Path
from typing import List

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from elfienest.cli import admin_commands
from elfienest.operations.admin_service import AdminAccount, DatabaseOperationError
from elfienest.operations.service_lifecycle import (
    ServiceLifecycleResult,
    ServicePortsActiveError,
)


@pytest.fixture(autouse=True)
def _isolate_recovery_lock(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        admin_commands,
        "admin_recovery_lock",
        lambda _home: nullcontext(),
    )


def test_reset_password_mismatch_fails_before_service_stop(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    passwords = iter(("first-password", "different-password"))
    stops: list[str] = []
    account = AdminAccount(user_id=1, username="admin", created_at=None)
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(
        admin_commands,
        "input_password",
        lambda _prompt: next(passwords),
        raising=False,
    )
    monkeypatch.setattr(
        admin_commands,
        "stop_managed_service",
        lambda: stops.append("stop"),
        raising=False,
    )

    # When
    exit_code = admin_commands.reset_password_interactive("admin")

    # Then
    assert exit_code == 1
    assert stops == []


def test_reset_password_runs_stop_reset_start_in_order_without_leaking_password(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    # Given
    password = "new-local-password"
    passwords = iter((password, password))
    calls: List[str] = []
    account = AdminAccount(user_id=1, username="doctor-bai", created_at=None)
    monkeypatch.setattr(
        admin_commands, "input_password", lambda _prompt: next(passwords)
    )
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(
        admin_commands,
        "stop_managed_service",
        lambda: (
            calls.append("stop")
            or ServiceLifecycleResult(
                status="stopped",
                command=("python", "scripts/serve.py", "--port", "8100"),
            )
        ),
    )
    monkeypatch.setattr(
        admin_commands,
        "reset_admin_password",
        lambda _path, _username, _password: calls.append("reset") or account,
    )
    monkeypatch.setattr(
        admin_commands,
        "start_managed_service",
        lambda command: (
            calls.append(f"start:{command[-1]}")
            or ServiceLifecycleResult(status="started")
        ),
    )

    # When
    exit_code = admin_commands.reset_password_interactive(None, "/tmp/test.db")

    # Then
    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls == ["stop", "reset", "start:8100"]
    assert "doctor-bai" in output
    assert password not in output


def test_reset_password_stops_on_lifecycle_failure_before_database_write(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    passwords = iter(("new-password", "new-password"))
    writes: List[str] = []
    account = AdminAccount(user_id=1, username="admin", created_at=None)
    monkeypatch.setattr(
        admin_commands, "input_password", lambda _prompt: next(passwords)
    )
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(
        admin_commands,
        "stop_managed_service",
        lambda: ServiceLifecycleResult(
            status="failed", error=ServicePortsActiveError("缺少 PID")
        ),
    )
    monkeypatch.setattr(
        admin_commands,
        "reset_admin_password",
        lambda *_args: writes.append("reset"),
    )

    # When
    exit_code = admin_commands.reset_password_interactive("admin", "/tmp/test.db")

    # Then
    assert exit_code == 1
    assert writes == []


def test_reset_password_restarts_service_after_database_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    passwords = iter(("new-password", "new-password"))
    calls: List[str] = []
    account = AdminAccount(user_id=1, username="admin", created_at=None)
    monkeypatch.setattr(
        admin_commands, "input_password", lambda _prompt: next(passwords)
    )
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(
        admin_commands,
        "stop_managed_service",
        lambda: (
            calls.append("stop")
            or ServiceLifecycleResult(
                status="stopped", command=("python", "scripts/serve.py")
            )
        ),
    )

    def fail_reset(_path: str, _username: str, _password: str) -> AdminAccount:
        calls.append("reset")
        raise DatabaseOperationError(Path(_path), "locked")

    monkeypatch.setattr(admin_commands, "reset_admin_password", fail_reset)
    monkeypatch.setattr(
        admin_commands,
        "start_managed_service",
        lambda _command: (
            calls.append("start") or ServiceLifecycleResult(status="started")
        ),
    )

    # When
    exit_code = admin_commands.reset_password_interactive("admin", "/tmp/test.db")

    # Then
    assert exit_code == 1
    assert calls == ["stop", "reset", "start"]


def test_reset_password_reports_updated_credentials_when_restart_fails(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    # Given
    passwords = iter(("new-password", "new-password"))
    account = AdminAccount(user_id=1, username="admin", created_at=None)
    monkeypatch.setattr(
        admin_commands, "input_password", lambda _prompt: next(passwords)
    )
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(
        admin_commands,
        "stop_managed_service",
        lambda: ServiceLifecycleResult(
            status="stopped", command=("python", "scripts/serve.py")
        ),
    )
    monkeypatch.setattr(admin_commands, "reset_admin_password", lambda *_args: account)
    monkeypatch.setattr(
        admin_commands,
        "start_managed_service",
        lambda _command: ServiceLifecycleResult(
            status="failed", error=ServicePortsActiveError("health timeout")
        ),
    )

    # When
    exit_code = admin_commands.reset_password_interactive("admin", "/tmp/test.db")

    # Then
    assert exit_code == 1
    assert "密码已更新，但服务恢复失败" in capsys.readouterr().out


def test_reset_password_cancelled_input_does_not_stop_service(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    stops: List[str] = []
    account = AdminAccount(user_id=1, username="admin", created_at=None)
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(admin_commands, "input_password", lambda _prompt: None)
    monkeypatch.setattr(
        admin_commands,
        "stop_managed_service",
        lambda: stops.append("stop"),
    )

    # When
    exit_code = admin_commands.reset_password_interactive("admin", "/tmp/test.db")

    # Then
    assert exit_code == 1
    assert stops == []


def test_reset_password_fails_closed_when_hidden_input_is_unavailable(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    account = AdminAccount(user_id=1, username="admin", created_at=None)
    stops: List[str] = []
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(
        admin_commands,
        "input_password",
        lambda _prompt: (_ for _ in ()).throw(getpass.GetPassWarning("no tty")),
    )
    monkeypatch.setattr(
        admin_commands,
        "stop_managed_service",
        lambda: stops.append("stop"),
    )

    # When
    exit_code = admin_commands.reset_password_interactive("admin", "/tmp/test.db")

    # Then
    assert exit_code == 1
    assert stops == []
