from __future__ import annotations

from argparse import Namespace

import pytest
from _pytest.capture import CaptureFixture

from app.orchestration.lifecycle.target_resolution import TargetNotFound
from scripts import elfienest


def test_dispatch_reports_keyboard_interrupt_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    # Given
    def interrupt(_lifecycle, *_args, **_kwargs) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(elfienest, "restart_background_service", interrupt)

    # When / Then
    with pytest.raises(SystemExit) as error:
        elfienest.dispatch_command(Namespace(command="restart"))
    assert error.value.code == 130
    assert "Cancelled" in capsys.readouterr().out


def test_dispatch_does_not_call_a_missing_target_an_unresolved_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    def no_target(*_args, **_kwargs) -> None:
        raise TargetNotFound("status", "默认数据目录不符合该命令的运行条件")

    monkeypatch.setattr(elfienest, "resolve_cli_target", no_target)

    with pytest.raises(SystemExit) as error:
        elfienest.dispatch_command(Namespace(command="status"))

    assert error.value.code == 2
    stderr = capsys.readouterr().err
    assert "status 没有可操作的数据任务" in stderr
    assert "target data root is unresolved" not in stderr
