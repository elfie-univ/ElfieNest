from __future__ import annotations

import getpass
import warnings

from _pytest.monkeypatch import MonkeyPatch

from app.interfaces.cli.tui import common
from app.interfaces.cli.tui.config_editors import config_llm
from ai_runtime.lab.menu import MenuItem, TerminalMenu


def test_input_password_fails_closed_when_getpass_cannot_hide_input(
    monkeypatch: MonkeyPatch,
) -> None:
    def warn_about_visible_input(_prompt: str, *, stream=None) -> str:
        del stream
        warnings.warn("no tty", getpass.GetPassWarning, stacklevel=2)
        return "visible-secret"

    monkeypatch.setattr(common.getpass, "getpass", warn_about_visible_input)

    assert common.input_password("Password") is None


def test_input_text_returns_none_on_eof(monkeypatch: MonkeyPatch) -> None:
    def raise_eof(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    assert common.input_text("Owner") is None


def test_terminal_menu_line_mode_returns_none_on_eof() -> None:
    def raise_eof(_prompt: str) -> str:
        raise EOFError

    menu = TerminalMenu(
        input_fn=raise_eof,
        output_fn=lambda _message: None,
        interactive=False,
    )

    assert menu.choose("Menu", (MenuItem("1", "Continue"),)) is None


def test_terminal_menu_read_text_returns_none_on_eof() -> None:
    def raise_eof(_prompt: str) -> str:
        raise EOFError

    menu = TerminalMenu(
        input_fn=raise_eof,
        output_fn=lambda _message: None,
        interactive=False,
    )

    assert menu.read_text("Input") is None


def test_config_llm_stops_cleanly_when_model_input_hits_eof(
    monkeypatch: MonkeyPatch,
) -> None:
    inputs = iter(["1"])

    def read_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr("builtins.input", read_input)
    monkeypatch.setattr("app.interfaces.cli.tui.config_editors.clear_screen", lambda: None)
    monkeypatch.setattr("app.interfaces.cli.tui.config_editors.print_banner", lambda: None)

    config_llm({})
