from __future__ import annotations

from pathlib import Path

import pytest

from app.bootstrap import diagnostics as diagnostics_bootstrap


class _RecordingDiagnostics:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def configure_root_warning_log(self) -> None:
        self.calls.append("root-log")

    def install_exception_hooks(self) -> None:
        self.calls.append("exception-hooks")

    def start_resource_monitor(self) -> None:
        self.calls.append("resource-monitor")

    def close(self) -> None:
        self.calls.append("close")


def test_open_core_process_diagnostics_composes_the_managed_sink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    diagnostics = _RecordingDiagnostics()
    constructor_arguments: list[tuple[Path, str, str | None]] = []

    def construct(
        elfie_home: Path,
        *,
        role: str,
        source_revision: str | None,
    ) -> _RecordingDiagnostics:
        constructor_arguments.append((elfie_home, role, source_revision))
        return diagnostics

    monkeypatch.setattr(diagnostics_bootstrap, "ProcessDiagnostics", construct)

    opened = diagnostics_bootstrap.open_core_process_diagnostics(
        tmp_path,
        source_revision="abc123",
    )

    assert opened is diagnostics
    assert constructor_arguments == [(tmp_path, "core", "abc123")]
    assert diagnostics.calls == [
        "root-log",
        "exception-hooks",
        "resource-monitor",
    ]


def test_open_core_process_diagnostics_closes_partial_initialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    diagnostics = _RecordingDiagnostics()

    def fail_resource_monitor() -> None:
        diagnostics.calls.append("resource-monitor")
        raise RuntimeError("monitor unavailable")

    diagnostics.start_resource_monitor = fail_resource_monitor  # type: ignore[method-assign]
    monkeypatch.setattr(
        diagnostics_bootstrap,
        "ProcessDiagnostics",
        lambda *_args, **_kwargs: diagnostics,
    )

    with pytest.raises(RuntimeError, match="monitor unavailable"):
        diagnostics_bootstrap.open_core_process_diagnostics(tmp_path)

    assert diagnostics.calls == [
        "root-log",
        "exception-hooks",
        "resource-monitor",
        "close",
    ]
