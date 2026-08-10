"""Focused tests for packaged Desktop host mechanics."""

from pathlib import Path

from infrastructure.platform.lifecycle.desktop import LocalDesktopHostAdapter


def test_desktop_adapter_discovers_configured_executable(
    monkeypatch, tmp_path: Path
) -> None:
    executable = tmp_path / "ElfieNestDesktop"
    executable.write_text("binary", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setenv("ELFIENEST_DESKTOP_BIN", str(executable))

    assert LocalDesktopHostAdapter().find_executable(tmp_path) == executable


def test_desktop_receipt_clears_stale_pid(monkeypatch, tmp_path: Path) -> None:
    adapter = LocalDesktopHostAdapter()
    adapter.write_receipt(tmp_path, 321)
    monkeypatch.setattr(adapter, "exists", lambda pid: False)

    assert adapter.process_id(tmp_path) is None
    assert not (tmp_path / "runtime" / "desktop.pid").exists()
