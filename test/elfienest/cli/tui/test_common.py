from __future__ import annotations

import getpass
import warnings

from _pytest.monkeypatch import MonkeyPatch

from elfienest.cli.tui import common


def test_input_password_fails_closed_when_getpass_cannot_hide_input(
    monkeypatch: MonkeyPatch,
) -> None:
    def warn_about_visible_input(_prompt: str) -> str:
        warnings.warn("no tty", getpass.GetPassWarning, stacklevel=2)
        return "visible-secret"

    monkeypatch.setattr(common.getpass, "getpass", warn_about_visible_input)

    assert common.input_password("Password") is None
