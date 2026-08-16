from __future__ import annotations

from dataclasses import dataclass

from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ComponentSnapshot,
    ComponentState,
    OwnerLease,
    RuntimeComponent,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
)
from app.orchestration.lifecycle.world_worker import RuntimeWorldWorker


class MemoryRecord:
    def __init__(self, value: RuntimeSnapshotV1) -> None:
        self.value = value

    def read(self) -> RuntimeSnapshotV1:
        return self.value

    def write(self, snapshot: RuntimeSnapshotV1) -> None:
        self.value = snapshot


@dataclass
class Process:
    pid: int

    def poll(self) -> None:
        return None


class AuthorityHost:
    def __init__(self, process: Process) -> None:
        self.process = process
        self.started = 0
        self.stopped: list[int] = []

    def start(self) -> Process:
        self.started += 1
        return self.process

    def stop(self, process: Process) -> None:
        self.stopped.append(process.pid)


class CrashingProcess(Process):
    def __init__(self, pid: int) -> None:
        super().__init__(pid)
        self.poll_count = 0

    def poll(self) -> int | None:
        self.poll_count += 1
        return None if self.poll_count == 1 else 1


def _core_snapshot() -> RuntimeSnapshotV1:
    return RuntimeSnapshotV1(
        instance_id="instance",
        generation=4,
        revision=3,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        desired_target=RuntimeTarget.NORMAL,
        reached_target=RuntimeTarget.CORE,
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, ComponentState.READY),
            ComponentSnapshot(RuntimeComponent.GATEWAY, ComponentState.READY),
        ),
        owner_lease=OwnerLease("core", 4),
    )


def test_worker_converges_world_after_core_without_blocking_core_state() -> None:
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(Process(9001))
    readiness = iter((False, True))
    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=lambda: next(readiness),
        sleeper=lambda _seconds: None,
    )

    worker._converge(snapshot)

    assert host.started == 1
    assert record.read().tier is BackendTier.WORLD_READY
    assert record.read().phase is RuntimePhase.WORLD_READY
    assert (
        record.read().component(RuntimeComponent.GODOT_AUTHORITY).state
        is ComponentState.READY
    )


def test_worker_world_failure_preserves_core_and_stops_only_authority() -> None:
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(Process(9002))
    clock = iter((False, False))
    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=lambda: next(clock),
        authority_timeout_seconds=0.0,
        sleeper=lambda _seconds: None,
    )

    worker._converge(snapshot)

    assert host.stopped == [9002]
    assert record.read().tier is BackendTier.CORE_READY
    assert record.read().phase is RuntimePhase.FAILED
    assert (
        record.read().component(RuntimeComponent.GODOT_AUTHORITY).state
        is ComponentState.FAILED
    )


def test_worker_retries_world_convergence_with_a_bounded_budget() -> None:
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(Process(9003))
    readiness = iter((False, True, True))
    worker_holder: list[RuntimeWorldWorker] = []
    sleep_count = [0]

    def stop_watchdog(_seconds: float) -> None:
        sleep_count[0] += 1
        if sleep_count[0] >= 2:
            worker_holder[0]._stop_event.set()

    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=lambda: next(readiness),
        authority_timeout_seconds=0.0,
        retry_delay_seconds=0.0,
        max_attempts=3,
        sleeper=stop_watchdog,
    )
    worker_holder.append(worker)

    worker._run()

    assert host.started == 2
    assert record.read().tier is BackendTier.WORLD_READY


def test_worker_watchdog_demotes_world_after_authority_crash() -> None:
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(CrashingProcess(9004))
    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=lambda: True,
        authority_timeout_seconds=0.0,
        max_attempts=1,
        sleeper=lambda _seconds: None,
    )

    worker._run()

    assert host.started == 1
    assert host.stopped == [9004]
    assert record.read().tier is BackendTier.CORE_READY
    assert record.read().phase is RuntimePhase.FAILED
    assert record.read().failures[0].code == "AUTHORITY_EXITED"
