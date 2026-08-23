from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from app.orchestration.lifecycle.ports import (
    LifecycleLease,
    LocalProcessEntry,
    ProcessSnapshot,
)
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ComponentSnapshot,
    ComponentState,
    EndpointSnapshot,
    RuntimeComponent,
    RuntimePhase,
    RuntimeSnapshotV1,
)
from app.orchestration.lifecycle.types import RecoveryInProgressError


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration


class FakeLease:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeRecoveryLock:
    def __init__(self, *, blocked: bool = False) -> None:
        self.blocked = blocked
        self.lease = FakeLease()

    def acquire_start_lease(
        self, elfie_home: Path, *, blocking: bool = False
    ) -> LifecycleLease:
        if self.blocked:
            raise RecoveryInProgressError(elfie_home / "runtime" / "locks" / "lock")
        return self.lease

    def recovery_is_active(self, elfie_home: Path) -> bool:
        return self.blocked

    @contextmanager
    def owner_recovery(self, elfie_home: Path):
        yield


class FakeProcessPort:
    def __init__(
        self,
        *,
        cwd: Path,
        command: Sequence[str] = ("python", "scripts/serve.py"),
        existence: Sequence[bool] = (True,),
        launched_pid: int = 5101,
        ports_active: bool = False,
        terminate_hook: Optional[Callable[[int, bool], None]] = None,
    ) -> None:
        self.cwd = cwd
        self.command = tuple(command)
        self.existence = list(existence)
        self.last_existence = self.existence[-1]
        self.launched_pid = launched_pid
        self.ports_active = ports_active
        self.terminate_hook = terminate_hook
        self.launches: list[tuple[tuple[str, ...], Path, Mapping[str, str]]] = []
        self.terminations: list[tuple[int, bool]] = []
        self.registration_error: Optional[OSError] = None
        self.read_error: Optional[OSError] = None

    def exists(self, pid: int) -> bool:
        if self.existence:
            self.last_existence = self.existence.pop(0)
        return self.last_existence

    def inspect(self, pid: int) -> ProcessSnapshot:
        return ProcessSnapshot(
            pid=pid,
            cwd=self.cwd,
            command=self.command,
            birth_identity=f"fake-{pid}",
        )

    def launch(
        self,
        command: Sequence[str],
        cwd: Path,
        *,
        environment: Optional[Mapping[str, str]] = None,
    ) -> int:
        self.launches.append((tuple(command), cwd, dict(environment or {})))
        return self.launched_pid

    def terminate(self, pid: int, *, force: bool = False) -> None:
        self.terminations.append((pid, force))
        if self.terminate_hook is not None:
            self.terminate_hook(pid, force)

    def ports_in_use(self, ports: Sequence[int]) -> bool:
        return self.ports_active

    def port_occupant_pid(self, port: int) -> Optional[int]:
        return self.launched_pid if self.ports_active else None

    def current_pid(self) -> int:
        return 1

    def list_processes(self) -> tuple[LocalProcessEntry, ...]:
        return ()

    def read_receipt(self, elfie_home: Path) -> Optional[str]:
        if self.read_error is not None:
            raise self.read_error
        try:
            return (elfie_home / "elfienest.pid").read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None

    def receipt_exists(self, elfie_home: Path) -> bool:
        return (elfie_home / "elfienest.pid").is_file()

    def register_receipt(self, elfie_home: Path, pid: int) -> Path:
        if self.registration_error is not None:
            raise self.registration_error
        elfie_home.mkdir(parents=True, exist_ok=True)
        path = elfie_home / "elfienest.pid"
        path.write_text(str(pid), encoding="utf-8")
        return path

    def remove_receipt(self, elfie_home: Path, pid: int) -> None:
        path = elfie_home / "elfienest.pid"
        try:
            if path.read_text(encoding="utf-8").strip() == str(pid):
                path.unlink()
        except FileNotFoundError:
            return

    def clear_receipt(self, elfie_home: Path) -> None:
        (elfie_home / "elfienest.pid").unlink(missing_ok=True)

    def register_current(self, elfie_home: Path) -> Path:
        return self.register_receipt(elfie_home, 1)

    def retain_current(self) -> None:
        return None


class MemoryRuntimeRecord:
    """Minimal authoritative snapshot used by lifecycle service tests."""

    def __init__(self, snapshot: RuntimeSnapshotV1) -> None:
        self.snapshot = snapshot

    def read(self) -> RuntimeSnapshotV1:
        return self.snapshot


def offline_runtime_record(
    *, endpoints: tuple[EndpointSnapshot, ...] = ()
) -> MemoryRuntimeRecord:
    return MemoryRuntimeRecord(
        RuntimeSnapshotV1(instance_id="test-instance", endpoints=endpoints)
    )


def active_runtime_record(
    *,
    pid: int,
    cwd: Path,
    command: Sequence[str],
    endpoints: tuple[EndpointSnapshot, ...] = (),
    executable: Optional[str] = None,
) -> MemoryRuntimeRecord:
    resolved_cwd = cwd.resolve()
    process_executable = executable or str(command[0])
    identity = f"fake-{pid}"
    component = ComponentSnapshot(
        RuntimeComponent.CORE,
        ComponentState.READY,
        pid=pid,
        executable=process_executable,
        birth_identity=identity,
        cwd=str(resolved_cwd),
    )
    gateway = ComponentSnapshot(
        RuntimeComponent.GATEWAY,
        ComponentState.READY,
        pid=pid,
        executable=process_executable,
        birth_identity=identity,
        cwd=str(resolved_cwd),
    )
    return MemoryRuntimeRecord(
        RuntimeSnapshotV1(
            instance_id="test-instance",
            generation=1,
            tier=BackendTier.CORE_READY,
            phase=RuntimePhase.CORE_READY,
            components=(component, gateway),
            endpoints=endpoints,
        )
    )


def write_pid(elfie_home: Path, pid: int) -> Path:
    elfie_home.mkdir(parents=True, exist_ok=True)
    path = elfie_home / "elfienest.pid"
    path.write_text(str(pid), encoding="utf-8")
    return path


def serve_command(project_root: Path) -> tuple[str, ...]:
    return ("python", str((project_root / "scripts" / "serve.py").resolve()))
