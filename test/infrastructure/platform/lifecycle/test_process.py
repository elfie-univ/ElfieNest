"""Focused tests for local lifecycle process mechanics."""

import os
import signal
from pathlib import Path

from infrastructure.platform.lifecycle.process import LocalServiceProcessAdapter


class _Inspector:
    def exists(self, pid: int) -> bool:
        return pid == 17

    def cwd(self, pid: int) -> Path:
        assert pid == 17
        return Path("/tmp/project")

    def command(self, pid: int) -> tuple[str, ...]:
        assert pid == 17
        return ("python", "scripts/serve.py")


def test_process_adapter_returns_a_strict_snapshot() -> None:
    adapter = LocalServiceProcessAdapter(_Inspector())

    snapshot = adapter.inspect(17)

    assert snapshot.pid == 17
    assert snapshot.cwd == Path("/tmp/project")
    assert snapshot.command == ("python", "scripts/serve.py")


def test_process_adapter_pid_receipt_is_owned_and_private(tmp_path: Path) -> None:
    adapter = LocalServiceProcessAdapter()

    pid_path = adapter.register_receipt(tmp_path, 424242)

    assert pid_path.read_text(encoding="utf-8") == "424242"
    assert pid_path.stat().st_mode & 0o777 == 0o600
    adapter.remove_receipt(tmp_path, 7)
    assert pid_path.exists()
    adapter.remove_receipt(tmp_path, 424242)
    assert not pid_path.exists()


def test_process_adapter_terminates_the_managed_process_group(monkeypatch) -> None:
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        os,
        "killpg",
        lambda process_group, requested_signal: signals.append(
            (process_group, requested_signal)
        ),
    )

    LocalServiceProcessAdapter().terminate(17)

    assert signals == [(17, signal.SIGTERM)]
