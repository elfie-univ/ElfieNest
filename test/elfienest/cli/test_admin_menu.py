from __future__ import annotations

from pathlib import Path
from typing import List

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from elfienest.cli import admin_commands


def test_show_admin_accounts_reports_missing_database_without_creating_it(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    db_path = tmp_path / "missing.db"

    exit_code = admin_commands.show_admin_accounts(str(db_path))

    assert exit_code == 1
    assert not db_path.exists()
    assert "数据库文件不可用" in capsys.readouterr().out


def test_admin_menu_can_show_accounts_and_return(monkeypatch: MonkeyPatch) -> None:
    choices = iter(("1", "0"))
    calls: list[str] = []
    monkeypatch.setattr("builtins.input", lambda _prompt: next(choices))
    monkeypatch.setattr(
        admin_commands,
        "show_admin_accounts",
        lambda: calls.append("show") or 0,
    )

    exit_code = admin_commands.run_admin_menu()

    assert exit_code == 0
    assert calls == ["show"]


def test_admin_menu_eof_returns_failure(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: (_ for _ in ()).throw(EOFError()),
    )

    assert admin_commands.run_admin_menu() == 1


def test_admin_menu_accepts_username_for_password_reset(
    monkeypatch: MonkeyPatch,
) -> None:
    choices = iter(("2", "doctor-bai", "0"))
    usernames: List[str | None] = []
    monkeypatch.setattr("builtins.input", lambda _prompt: next(choices))
    monkeypatch.setattr(
        admin_commands,
        "reset_password_interactive",
        lambda username: usernames.append(username) or 0,
    )

    exit_code = admin_commands.run_admin_menu()

    assert exit_code == 0
    assert usernames == ["doctor-bai"]


def test_admin_menu_returns_last_reset_failure(monkeypatch: MonkeyPatch) -> None:
    choices = iter(("2", "doctor-bai", "0"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(choices))
    monkeypatch.setattr(admin_commands, "reset_password_interactive", lambda _name: 1)

    assert admin_commands.run_admin_menu() == 1


def test_dispatch_admin_routes_reset_password_with_username(
    monkeypatch: MonkeyPatch,
) -> None:
    usernames: list[str | None] = []
    monkeypatch.setattr(
        admin_commands,
        "reset_password_interactive",
        lambda username: usernames.append(username) or 0,
    )

    exit_code = admin_commands.dispatch_admin("reset-password", "doctor-bai")

    assert exit_code == 0
    assert usernames == ["doctor-bai"]
