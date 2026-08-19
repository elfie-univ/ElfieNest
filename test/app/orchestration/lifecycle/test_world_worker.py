from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import call, patch

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
    def __init__(
        self, process: Process, stop_failure: RuntimeError | None = None
    ) -> None:
        self.process = process
        self.started = 0
        self.stopped: list[int] = []
        self.stop_failure = stop_failure

    def start(self) -> Process:
        self.started += 1
        return self.process

    def stop(self, process: Process) -> None:
        self.stopped.append(process.pid)
        if self.stop_failure is not None:
            raise self.stop_failure


class CrashingProcess(Process):
    def __init__(self, pid: int) -> None:
        super().__init__(pid)
        self.poll_count = 0

    def poll(self) -> int | None:
        self.poll_count += 1
        return None if self.poll_count == 1 else 1


@dataclass
class FakeClock:
    now: float = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


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


def test_worker_retries_world_convergence_slowly_with_a_bounded_budget() -> None:
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(Process(9003))

    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=lambda: False,
        authority_timeout_seconds=-1.0,
        sleeper=lambda _seconds: None,
    )

    with patch.object(worker._stop_event, "wait", return_value=False) as retry_wait:
        worker._run()

    assert host.started == 3
    assert host.stopped == [9003, 9003, 9003]
    assert retry_wait.call_args_list == [call(10.0), call(10.0)]
    assert record.read().tier is BackendTier.CORE_READY
    assert record.read().phase is RuntimePhase.FAILED
    assert record.read().failures[0].code == "WORLD_READY_TIMEOUT"


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


def test_worker_watchdog_tolerates_a_transient_readiness_gap() -> None:
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(Process(9007))
    clock = FakeClock()
    probe_count = [0]
    worker_holder: list[RuntimeWorldWorker] = []

    def readiness() -> bool:
        probe_count[0] += 1
        if probe_count[0] == 1:
            return True
        if clock.now < 5.0:
            return False
        worker_holder[0]._stop_event.set()
        return True

    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=readiness,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )
    worker_holder.append(worker)

    worker._converge(snapshot)
    worker._watch_world(record.read())

    assert clock.now >= 5.0
    assert host.stopped == []
    assert record.read().tier is BackendTier.WORLD_READY
    assert record.read().phase is RuntimePhase.WORLD_READY


def test_worker_watchdog_demotes_world_after_ten_second_readiness_gap() -> None:
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(Process(9008))
    clock = FakeClock()
    probe_count = [0]

    def readiness() -> bool:
        probe_count[0] += 1
        return probe_count[0] == 1

    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=readiness,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    worker._converge(snapshot)
    worker._watch_world(record.read())

    assert 10.0 <= clock.now < 10.2
    assert host.stopped == [9008]
    assert record.read().tier is BackendTier.CORE_READY
    assert record.read().phase is RuntimePhase.FAILED
    assert record.read().failures[0].code == "WORLD_DISCONNECTED"


def test_worker_stop_publishes_core_ready_after_releasing_world() -> None:
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(Process(9005))
    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=lambda: True,
        sleeper=lambda _seconds: None,
    )

    worker._converge(snapshot)
    detail = worker.stop()

    assert detail is None
    assert host.stopped == [9005]
    assert record.read().tier is BackendTier.CORE_READY
    assert record.read().phase is RuntimePhase.CORE_READY
    authority = record.read().component(RuntimeComponent.GODOT_AUTHORITY)
    assert authority.state is ComponentState.ABSENT
    assert authority.pid is None


def test_worker_stop_keeps_explicit_residual_evidence_when_authority_rejects_stop() -> (
    None
):
    snapshot = _core_snapshot()
    record = MemoryRecord(snapshot)
    host = AuthorityHost(
        Process(9006), stop_failure=RuntimeError("authority is unresponsive")
    )
    worker = RuntimeWorldWorker(
        runtime_record=record,
        authority_host=host,
        world_ready_probe=lambda: True,
        sleeper=lambda _seconds: None,
    )

    worker._converge(snapshot)
    detail = worker.stop()

    assert detail == "authority is unresponsive"
    assert record.read().tier is BackendTier.OFFLINE
    assert record.read().phase is RuntimePhase.FAILED
    assert record.read().failures[0].code == "WORLD_STOP_INCOMPLETE"
    authority = record.read().component(RuntimeComponent.GODOT_AUTHORITY)
    assert authority.state is ComponentState.FAILED
    assert authority.pid == 9006
