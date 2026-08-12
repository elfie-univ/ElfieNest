from __future__ import annotations

from argparse import Namespace

import pytest
from _pytest.capture import CaptureFixture

from scripts import elfienest


def test_dispatch_reports_keyboard_interrupt_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    # Given
    def interrupt(_lifecycle) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(elfienest, "restart_background_service", interrupt)

    # When / Then
    with pytest.raises(SystemExit) as error:
        elfienest.dispatch_command(Namespace(command="restart"))
    assert error.value.code == 130
    assert "Cancelled" in capsys.readouterr().out
