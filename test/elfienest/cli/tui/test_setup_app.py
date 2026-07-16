from __future__ import annotations

import builtins
import sqlite3
from pathlib import Path

from _pytest.capture import CaptureFixture

from elfienest.cli.tui import setup_app
from runtime.storage.data_home import get_db_path


def test_run_setup_wizard_creates_first_owner(
    tmp_path: Path,
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    monkeypatch.setattr(setup_app, "clear_screen", lambda: None)
    monkeypatch.setattr(setup_app, "print_banner", lambda: None)
    monkeypatch.setattr(setup_app, "input_password", lambda _prompt: "setup-secret")
    _patch_input(monkeypatch, ["owner", "n"])

    setup_app.run_setup_wizard()

    with sqlite3.connect(get_db_path()) as conn:
        owner_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE username='owner' AND role='owner'"
        ).fetchone()[0]

    output = capsys.readouterr().out
    assert owner_count == 1
    assert "设置完成" in output
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
    _patch_input(monkeypatch, ["owner"])

    setup_app.run_setup_wizard()

    with sqlite3.connect(get_db_path()) as conn:
        owner_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert owner_count == 0
    assert "安全输入" in capsys.readouterr().out


def test_optional_provider_prompt_stops_cleanly_on_eof(monkeypatch) -> None:
    monkeypatch.setattr(setup_app, "read_user_config", lambda: {})
    monkeypatch.setattr(setup_app, "read_env_file", lambda: {})
    monkeypatch.setattr(setup_app, "write_user_config", lambda _config: None)
    monkeypatch.setattr(setup_app, "write_env_file", lambda _env: None)

    def raise_eof() -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    setup_app._configure_optional_providers(["openai"])


def _patch_input(
    monkeypatch,
    values: list[str],
) -> None:
    iterator = iter(values)

    def fake_input(prompt: str = "") -> str:
        return next(iterator)

    monkeypatch.setattr(builtins, "input", fake_input)
