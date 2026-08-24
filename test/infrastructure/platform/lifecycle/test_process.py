"""Focused tests for local lifecycle process mechanics."""

import os
import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_windows_process_identity_reader_uses_only_native_kernel_evidence(
    monkeypatch,
) -> None:
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
        process,
        "_windows_process_executable",
        lambda pid: rf"C:\Program Files\Ollama\ollama-{pid}.exe",
        raising=False,
    )
    monkeypatch.setattr(
        process.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Windows process identity must not invoke CIM or ps")
        ),
    )

    identity = process.DefaultProcessIdentityReader().read(17)

    assert identity is not None
    assert identity.pid == 17
    assert identity.birth_identity == "win32-create:17"
    assert identity.executable == r"C:\Program Files\Ollama\ollama-17.exe"


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


def test_windows_process_query_converts_cim_timeout_to_stable_os_error(
    monkeypatch,
) -> None:
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(process.subprocess, "run", timeout)

    with pytest.raises(
        OSError,
        match=r"Windows process identity query timed out for PID 1872",
    ):
        process._windows_process_command(1872)


def test_windows_process_snapshot_reuses_one_cim_command_query(monkeypatch) -> None:
    real_os = process.os
    command = (r"C:\Program Files\ElfieNest\ElfieNestCore.exe", "--lan")
    calls: list[tuple[str, object]] = []

    class WindowsOsProxy:
        name = "nt"

        def __getattr__(self, attribute: str):
            return getattr(real_os, attribute)

    monkeypatch.setattr(process, "os", WindowsOsProxy())
    monkeypatch.setattr(
        process,
        "_windows_process_birth_identity",
        lambda pid: f"win32-create:{pid}",
    )
    monkeypatch.setattr(
        process,
        "_windows_process_command",
        lambda pid: calls.append(("command", pid)) or command,
    )
    monkeypatch.setattr(
        process,
        "_windows_process_cwd_from_command",
        lambda pid, observed: (
            calls.append(("cwd", observed)) or Path(r"C:\Program Files\ElfieNest")
        ),
        raising=False,
    )

    snapshot = process.DefaultProcessInspector().snapshot(17)

    assert snapshot.command == command
    assert snapshot.cwd == Path(r"C:\Program Files\ElfieNest")
    assert snapshot.birth_identity == "win32-create:17"
    assert calls == [("command", 17), ("cwd", command)]


def test_owned_windows_launch_uses_captured_command_without_cim_query(
    monkeypatch, tmp_path: Path
) -> None:
    command = (r"C:\Program Files\ElfieNest\ElfieNestCore.exe", "--lan")
    monkeypatch.setenv("ELFIENEST_RUNTIME_LOG", str(tmp_path / "runtime.log"))

    class Inspector:
        def birth_identity(self, pid: int) -> str:
            assert pid == 99
            return "win32-create:99"

        def cwd(self, _pid: int) -> Path:
            raise AssertionError("owned launch cwd must not invoke CIM")

        def command(self, _pid: int) -> tuple[str, ...]:
            raise AssertionError("owned launch command must not invoke CIM")

    class Process:
        pid = 99

    monkeypatch.setattr(
        process,
        "os",
        SimpleNamespace(name="nt", environ=os.environ),
    )
    monkeypatch.setattr(
        process.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )

    adapter = LocalServiceProcessAdapter(Inspector())
    pid = adapter.launch(command, tmp_path)
    snapshot = adapter.inspect(pid)

    assert snapshot.pid == 99
    assert snapshot.cwd == tmp_path.resolve()
    assert snapshot.command == command
    assert snapshot.birth_identity == "win32-create:99"


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


def test_managed_windows_core_retains_launcher_job_once(monkeypatch) -> None:
    calls: list[str] = []

    class Job:
        def close(self) -> None:
            calls.append("close")

    monkeypatch.setenv("ELFIENEST_JOB_NAME", r"Local\ElfieNest.core.test")
    monkeypatch.setattr(
        process,
        "os",
        SimpleNamespace(name="nt", environ=os.environ),
    )
    monkeypatch.setattr(
        process.WindowsJobObject,
        "open",
        classmethod(lambda _cls, name: calls.append(f"open:{name}") or Job()),
        raising=False,
    )
    adapter = LocalServiceProcessAdapter()
    adapter.retain_current()
    adapter.retain_current()

    assert calls == [r"open:Local\ElfieNest.core.test"]


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
