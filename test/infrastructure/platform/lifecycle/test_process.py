"""Focused tests for local lifecycle process mechanics."""

import os
import signal
from pathlib import Path
from types import SimpleNamespace

from infrastructure.platform.lifecycle import process
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


def test_windows_process_inspector_uses_native_birth_identity(monkeypatch) -> None:
    real_os = process.os

    class WindowsOsProxy:
        name = "nt"

        def __getattr__(self, attribute: str):
            return getattr(real_os, attribute)

    monkeypatch.setattr(process, "os", WindowsOsProxy())
    monkeypatch.setattr(
        process,
        "_windows_process_birth_identity",
        lambda pid: f"win32-create:{pid}",
        raising=False,
    )
    monkeypatch.setattr(
        process.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Windows birth identity must not invoke ps")
        ),
    )

    assert process.DefaultProcessInspector().birth_identity(17) == "win32-create:17"


def test_windows_process_inspector_uses_native_process_queries(monkeypatch) -> None:
    real_os = process.os

    class WindowsOsProxy:
        name = "nt"

        def __getattr__(self, attribute: str):
            return getattr(real_os, attribute)

    monkeypatch.setattr(process, "os", WindowsOsProxy())
    monkeypatch.setattr(
        process,
        "_windows_process_exists",
        lambda pid: pid == 17,
        raising=False,
    )
    monkeypatch.setattr(
        process,
        "_windows_process_command",
        lambda pid: (
            r"C:\Program Files\ElfieNest\resources\python-core\ElfieNestCore.exe",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        process,
        "_windows_process_cwd",
        lambda pid: Path(r"C:\Program Files\ElfieNest"),
        raising=False,
    )
    monkeypatch.setattr(
        process.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Windows process inspection must not invoke Unix tools")
        ),
    )
    inspector = process.DefaultProcessInspector()

    assert inspector.exists(17)
    assert inspector.command(17)[0].endswith("ElfieNestCore.exe")
    assert inspector.cwd(17) == Path(r"C:\Program Files\ElfieNest")


def test_process_adapter_pid_receipt_is_owned_and_private(tmp_path: Path) -> None:
    adapter = LocalServiceProcessAdapter()

    pid_path = adapter.register_receipt(tmp_path, 424242)

    assert pid_path.read_text(encoding="utf-8") == "424242"
    assert pid_path.stat().st_mode & 0o777 == 0o600
    adapter.remove_receipt(tmp_path, 7)
    assert pid_path.exists()
    adapter.remove_receipt(tmp_path, 424242)
    assert not pid_path.exists()


def test_process_adapter_skips_posix_fchmod_on_windows(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: Windows does not provide the POSIX fchmod operation.
    def unsupported_fchmod(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Windows must not call POSIX-only fchmod")

    real_os = process.os

    class WindowsOsProxy:
        name = "nt"

        def __getattr__(self, attribute: str):
            return getattr(real_os, attribute)

        @staticmethod
        def fchmod(*_args: object, **_kwargs: object) -> None:
            unsupported_fchmod()

    monkeypatch.setattr(process, "os", WindowsOsProxy())

    # When: the managed service writes its PID receipt.
    pid_path = LocalServiceProcessAdapter().register_receipt(tmp_path, 424242)

    # Then: the receipt is still created with the platform default ACL.
    assert pid_path.read_text(encoding="utf-8") == "424242"


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


def test_process_adapter_uses_taskkill_tree_on_windows(monkeypatch) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def run(command, **kwargs):
        calls.append((tuple(command), kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        process,
        "os",
        SimpleNamespace(name="nt", environ=os.environ),
    )
    monkeypatch.setattr(process.subprocess, "run", run)

    LocalServiceProcessAdapter().terminate(17, force=True)

    assert calls[0][0] == ("taskkill", "/PID", "17", "/T", "/F")
    assert calls[0][1]["timeout"] == 5.0


def test_process_adapter_starts_a_windows_process_group(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("ELFIENEST_RUNTIME_LOG", str(tmp_path / "runtime.log"))

    class Process:
        pid = 99

    def popen(_command, **kwargs):
        calls.append(kwargs)
        return Process()

    monkeypatch.setattr(
        process,
        "os",
        SimpleNamespace(name="nt", environ=os.environ),
    )
    monkeypatch.setattr(process.subprocess, "Popen", popen)

    pid = LocalServiceProcessAdapter().launch(("core",), tmp_path)

    assert pid == 99
    assert "start_new_session" not in calls[0]
    assert calls[0]["creationflags"] == getattr(
        process.subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )


def test_managed_service_log_rotates_before_a_new_process_owns_it(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs" / "service.log"
    log_path.parent.mkdir()
    log_path.write_bytes(b"old-storm")
    monkeypatch.setattr(process, "RUNTIME_LOG_MAX_BYTES", 4)
    monkeypatch.setattr(process, "RUNTIME_LOG_BACKUP_COUNT", 2)

    stream = process._open_runtime_log({"ELFIENEST_RUNTIME_LOG": str(log_path)})
    try:
        stream.write(b"new-run")
    finally:
        stream.close()

    assert log_path.read_bytes() == b"new-run"
    assert log_path.with_name("service.log.1").read_bytes() == b"old-storm"
    assert log_path.stat().st_mode & 0o777 == 0o600


def test_managed_core_console_has_a_separate_owned_log(tmp_path: Path) -> None:
    service_log = tmp_path / "logs" / "service.log"
    console_log = tmp_path / "logs" / "service-console.log"

    stream = process._open_runtime_log(
        {
            "ELFIENEST_RUNTIME_LOG": str(service_log),
            "ELFIENEST_RUNTIME_CONSOLE_LOG": str(console_log),
        }
    )
    try:
        stream.write(b"startup output")
    finally:
        stream.close()

    assert console_log.read_bytes() == b"startup output"
    assert service_log.exists() is False


def test_process_adapter_cleans_windows_job_after_graceful_stop(monkeypatch) -> None:
    calls: list[str] = []

    class Job:
        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(
        process,
        "os",
        SimpleNamespace(name="nt", environ=os.environ),
    )
    monkeypatch.setattr(
        process,
        "_terminate_windows_process_tree",
        lambda pid, force: calls.append(f"kill:{pid}:{force}"),
    )
    adapter = LocalServiceProcessAdapter()
    adapter._windows_jobs[17] = Job()

    adapter.terminate(17)

    assert calls == ["kill:17:False", "close"]


def test_process_adapter_kills_child_when_windows_job_attach_fails(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("ELFIENEST_RUNTIME_LOG", str(tmp_path / "runtime.log"))

    class Process:
        pid = 99

        def kill(self) -> None:
            calls.append("kill")

        def wait(self, timeout: float) -> int:
            calls.append(f"wait:{timeout}")
            return 1

    monkeypatch.setattr(
        process,
        "os",
        SimpleNamespace(name="nt", environ=os.environ),
    )
    monkeypatch.setattr(
        process.subprocess, "Popen", lambda *_args, **_kwargs: Process()
    )
    monkeypatch.setattr(
        process,
        "attach_process_to_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("job failed")),
    )

    try:
        LocalServiceProcessAdapter().launch(("core",), tmp_path)
    except OSError as error:
        assert str(error) == "job failed"
    else:
        raise AssertionError("launch must fail when the Job Object cannot attach")

    assert calls == ["kill", "wait:1.0"]
