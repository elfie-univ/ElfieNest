from __future__ import annotations

from pathlib import Path

from app.orchestration.lifecycle import desktop as desktop_lifecycle
from app.orchestration.lifecycle.types import ServiceLifecycleResult


def test_find_desktop_executable_prefers_explicit_runtime(tmp_path: Path, monkeypatch) -> None:
    # Given
    executable = tmp_path / "ElfieNestDesktop"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("ELFIENEST_DESKTOP_BIN", str(executable))

    # When / Then
    assert desktop_lifecycle.find_desktop_executable(tmp_path) == executable


def test_find_desktop_executable_discovers_a_packaged_macos_app(tmp_path: Path, monkeypatch) -> None:
    # Given: an unsigned internal-test macOS app bundle in the release directory.
    monkeypatch.delenv("ELFIENEST_DESKTOP_BIN", raising=False)
    executable = tmp_path / "dist" / "ElfieNest.app" / "Contents" / "MacOS" / "ElfieNest"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)

    # When/Then: the CLI discovery path resolves the actual bundled executable.
    assert desktop_lifecycle.find_desktop_executable(tmp_path) == executable


def test_stop_desktop_is_idempotent_without_pid_receipt(tmp_path: Path) -> None:
    # Given / When
    result = desktop_lifecycle.stop_desktop_application(tmp_path)

    # Then
    assert result == ServiceLifecycleResult(status="already_stopped")
