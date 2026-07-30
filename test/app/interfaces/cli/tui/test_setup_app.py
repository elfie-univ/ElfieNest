from __future__ import annotations

import builtins
import sqlite3
from pathlib import Path

from _pytest.capture import CaptureFixture

from ai_runtime.storage.data_home import get_db_path
from app.interfaces.cli.tui import setup_app


def test_run_setup_wizard_creates_first_owner(
    tmp_path: Path,
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    monkeypatch.setattr(setup_app, "clear_screen", lambda: None)
    monkeypatch.setattr(setup_app, "print_banner", lambda: None)
    monkeypatch.setattr(setup_app, "input_password", lambda _prompt: "setup-secret")
    _patch_input(monkeypatch, ["y", "owner", "Owner", "skip", "4", "skip", "y"])

    setup_app.run_setup_wizard()

    with sqlite3.connect(get_db_path()) as conn:
        owner_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE username='owner' AND role='owner'"
        ).fetchone()[0]

    output = capsys.readouterr().out
    assert owner_count == 1
    assert "Setup complete" in output
    assert "Step 5/5" in output
    assert "setup-secret" not in output


def test_run_setup_wizard_fails_closed_without_hidden_password_input(
    tmp_path: Path,
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    monkeypatch.setattr(setup_app, "clear_screen", lambda: None)
    monkeypatch.setattr(setup_app, "print_banner", lambda: None)
    monkeypatch.setattr(
        setup_app,
        "input_password",
        lambda _prompt: None,
    )
    _patch_input(monkeypatch, ["y", "owner", "Owner"])

    setup_app.run_setup_wizard()

    with sqlite3.connect(get_db_path()) as conn:
        owner_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert owner_count == 0
    assert "Cannot safely input" in capsys.readouterr().out


def test_tui_invalid_ollama_choice_does_not_advance_setup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """无效输入不能把终端向导越过 Ollama 选择步骤。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    monkeypatch.setattr(setup_app, "clear_screen", lambda: None)
    monkeypatch.setattr(setup_app, "print_banner", lambda: None)
    monkeypatch.setattr(setup_app, "input_password", lambda _prompt: "setup-secret")
    _patch_input(monkeypatch, ["y", "owner", "Owner", "not-a-choice"])

    setup_app.run_setup_wizard()

    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute(
            "SELECT owner_user_id, setup_step FROM local_installations "
            "WHERE installation_id = 'local'"
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] == "owner"


def _patch_input(
    monkeypatch,
    values: list[str],
) -> None:
    iterator = iter(values)

    def fake_input(prompt: str = "") -> str:
        return next(iterator)

    monkeypatch.setattr(builtins, "input", fake_input)
