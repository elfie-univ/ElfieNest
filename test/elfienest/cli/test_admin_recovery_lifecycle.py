from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from elfienest.cli import admin_commands
from elfienest.operations.admin_service import AdminAccount
from elfienest.operations.service_lifecycle import ServiceLifecycleResult


def test_reset_password_releases_recovery_lock_before_service_restart(
    monkeypatch: MonkeyPatch,
) -> None:
    password = "new-local-password"
    account = AdminAccount(user_id=1, username="doctor-bai", created_at=None)
    calls: List[str] = []

    @contextmanager
    def recording_lock(_home: Path) -> Iterator[None]:
        calls.append("lock-enter")
        try:
            yield
        finally:
            calls.append("lock-exit")

    passwords = iter((password, password))
    monkeypatch.setattr(
        admin_commands, "input_password", lambda _prompt: next(passwords)
    )
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(admin_commands, "admin_recovery_lock", recording_lock)
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
    monkeypatch.setattr(
        admin_commands,
        "reset_admin_password",
        lambda *_args: calls.append("reset") or account,
    )
    monkeypatch.setattr(
        admin_commands,
        "start_managed_service",
        lambda _command: (
            calls.append("start") or ServiceLifecycleResult(status="started")
        ),
    )

    exit_code = admin_commands.reset_password_interactive(None, "/tmp/test.db")

    assert exit_code == 0
    assert calls == ["lock-enter", "stop", "reset", "lock-exit", "start"]


def test_reset_password_reports_recovery_lock_io_failure(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    account = AdminAccount(user_id=1, username="admin", created_at=None)
    passwords = iter(("new-password", "new-password"))

    @contextmanager
    def inaccessible_lock(_home: Path) -> Iterator[None]:
        raise PermissionError("lock denied")
        yield

    monkeypatch.setattr(
        admin_commands, "input_password", lambda _prompt: next(passwords)
    )
    monkeypatch.setattr(admin_commands, "list_admin_accounts", lambda _path: (account,))
    monkeypatch.setattr(admin_commands, "admin_recovery_lock", inaccessible_lock)

    exit_code = admin_commands.reset_password_interactive("admin", "/tmp/test.db")

    assert exit_code == 1
    assert "无法开始管理员恢复" in capsys.readouterr().out
