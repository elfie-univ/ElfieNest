"""Tests for the repository-wide test environment preflight."""

from __future__ import annotations

import errno
from typing import Optional, Tuple

from scripts.quality.checks import environment as check_quality_environment


class _FakeSocket:
    def __init__(self, error: Optional[BaseException] = None) -> None:
        self.error = error
        self.closed = False
        self.bound: Optional[Tuple[str, int]] = None

    def bind(self, address: Tuple[str, int]) -> None:
        if self.error is not None:
            raise self.error
        self.bound = address

    def close(self) -> None:
        self.closed = True


def test_probe_reports_allowed_loopback_bind() -> None:
    fake = _FakeSocket()

    result = check_quality_environment.probe_loopback_bind(
        lambda *_args: fake,
    )

    assert result.status == "allowed"
    assert result.reason == "ok"
    assert result.exit_code == 0
    assert fake.bound == ("127.0.0.1", 0)
    assert fake.closed


def test_probe_classifies_permission_denial_as_environment_block() -> None:
    fake = _FakeSocket(PermissionError(errno.EPERM, "operation not permitted"))

    result = check_quality_environment.probe_loopback_bind(
        lambda *_args: fake,
    )

    assert result.status == "blocked"
    assert result.reason == "permission_denied"
    assert result.error_number == errno.EPERM
    assert result.exit_code == 2
    assert fake.closed


def test_probe_keeps_unexpected_socket_errors_as_failures() -> None:
    fake = _FakeSocket(OSError(errno.EADDRNOTAVAIL, "address unavailable"))

    result = check_quality_environment.probe_loopback_bind(
        lambda *_args: fake,
    )

    assert result.status == "error"
    assert result.reason == "socket_probe_failed"
    assert result.error_number == errno.EADDRNOTAVAIL
    assert result.exit_code == 1


def test_main_json_output_is_machine_readable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_quality_environment,
        "probe_loopback_bind",
        lambda: check_quality_environment.QualityEnvironmentResult(
            status="blocked",
            reason="permission_denied",
            error_number=errno.EPERM,
            detail="operation not permitted",
        ),
    )

    assert check_quality_environment.main(["--json"]) == 2
    assert capsys.readouterr().out.strip() == (
        '{"capability": "localhost_bind", "detail": "operation not permitted", '
        '"errno": 1, "reason": "permission_denied", "status": "blocked"}'
    )
