from __future__ import annotations

from pathlib import Path

from elfienest.operations import desktop_lifecycle
from elfienest.operations.service_lifecycle_types import ServiceLifecycleResult


def test_find_desktop_executable_prefers_explicit_runtime(tmp_path: Path, monkeypatch) -> None:
    # Given
    executable = tmp_path / "ElfieNestDesktop"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("ELFIENEST_DESKTOP_BIN", str(executable))

    # When / Then
    assert desktop_lifecycle.find_desktop_executable(tmp_path) == executable


def test_stop_desktop_is_idempotent_without_pid_receipt(tmp_path: Path) -> None:
    # Given / When
    result = desktop_lifecycle.stop_desktop_application(tmp_path)

    # Then
    assert result == ServiceLifecycleResult(status="already_stopped")
