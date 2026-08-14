from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Optional

from app.orchestration.lifecycle.ports import AuthorityProcess
from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    OwnerLease,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
    RuntimeProgressPhase,
)
from app.orchestration.lifecycle.runtime_supervisor import RuntimeSupervisor
from app.orchestration.lifecycle.types import (
    AuthorityHostError,
    LaunchFailedError,
    ServiceLifecycleResult,
)
from test.app.orchestration.lifecycle.service_fakes import FakeClock


def _health(
    *,
    authority: RuntimeHealthState = RuntimeHealthState.READY,
    ollama: RuntimeHealthState = RuntimeHealthState.READY,
) -> RuntimeHealth:
    return RuntimeHealth(
        state=RuntimeHealthState.READY,
        generation=0,
        owner_lease=None,
        components=(
            ComponentHealth(RuntimeComponent.CORE, RuntimeHealthState.READY),
            ComponentHealth(RuntimeComponent.GATEWAY, RuntimeHealthState.READY),
            ComponentHealth(RuntimeComponent.GODOT_AUTHORITY, authority),
            ComponentHealth(RuntimeComponent.OLLAMA, ollama),
        ),
    )


class MemoryRecord:
    def __init__(self) -> None:
        self.value = RuntimeHealth(
            state=RuntimeHealthState.STOPPED,
            generation=0,
            owner_lease=None,
            components=(),
        )

    def read(self) -> RuntimeHealth:
        return self.value

    def write(self, health: RuntimeHealth) -> None:
        self.value = health

    def remove(self) -> None:
        self.__init__()


@dataclass
class Process:
    pid: int


class AuthorityHost:
    def __init__(
        self,
        *,
        process: Optional[AuthorityProcess] = None,
        failure: Optional[AuthorityHostError] = None,
        calls: Optional[list[str]] = None,
    ) -> None:
        self.process = process
        self.failure = failure
        self.calls = calls if calls is not None else []

    def start(self) -> Optional[AuthorityProcess]:
        self.calls.append("authority")
        if self.failure is not None:
            raise self.failure
        return self.process

    def stop(self, process: AuthorityProcess) -> None:
        self.calls.append(f"stop-authority:{process.pid}")


def _supervisor(
    *,
    record: Optional[MemoryRecord] = None,
    health_probe=_health,
    start_core=lambda healthy: ServiceLifecycleResult(status="started", pid=7101),
    stop_core=lambda: ServiceLifecycleResult(status="stopped", pid=7101),
    authority_host=None,
    **kwargs,
) -> RuntimeSupervisor:
    return RuntimeSupervisor(
        runtime_record=record or MemoryRecord(),
        health_probe=health_probe,
        start_core=start_core,
        stop_core=stop_core,
        authority_host=authority_host,
        **kwargs,
    )


def test_start_records_one_generation_and_degrades_only_for_ollama() -> None:
    starts: list[bool] = []
    supervisor = _supervisor(
        health_probe=lambda: _health(ollama=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            starts.append(healthy())
            or ServiceLifecycleResult(status="started", pid=7101)
        ),
    )

    result = supervisor.start(owner_id="cli")

    assert result.status == "started"
    assert starts == [True]
    health = supervisor.status()
    assert health.state is RuntimeHealthState.DEGRADED
    assert health.generation == 1
    assert health.owner_lease is not None
    assert health.owner_lease.owner_id == "cli"


def test_start_emits_progress_and_promotes_the_startup_claim() -> None:
    record = MemoryRecord()
    phases: list[RuntimeProgressPhase] = []
    supervisor = _supervisor(
        record=record,
        start_core=lambda healthy: (
            healthy() and ServiceLifecycleResult(status="started", pid=7111)
        ),
        progress_callback=phases.append,
    )

    result = supervisor.start(owner_id="desktop-progress")

    assert result.status == "started"
    assert phases[0] is RuntimeProgressPhase.STARTING
    assert RuntimeProgressPhase.CORE_READY in phases
    assert RuntimeProgressPhase.READY in phases
    assert phases.index(RuntimeProgressPhase.CORE_READY) < phases.index(
        RuntimeProgressPhase.READY
    )
    assert record.read().startup_owner_id is None
    assert record.read().owner_lease is not None
    assert record.read().owner_lease.owner_id == "desktop-progress"


def test_start_rejects_a_runtime_already_claimed_by_another_startup() -> None:
    record = MemoryRecord()
    record.write(
        RuntimeHealth(
            state=RuntimeHealthState.STARTING,
            generation=0,
            owner_lease=None,
            components=(),
            startup_owner_id="desktop-existing",
        )
    )
    calls: list[str] = []
    supervisor = _supervisor(
        record=record,
        start_core=lambda healthy: (
            calls.append("core") or ServiceLifecycleResult(status="started")
        ),
    )

    result = supervisor.start(owner_id="desktop-new")

    assert result.status == "failed"
    assert calls == []
    assert record.read().startup_owner_id == "desktop-existing"


def test_start_recovers_stale_owner_lease_without_a_live_core_receipt() -> None:
    record = MemoryRecord()
    record.write(
        replace(
            _health(authority=RuntimeHealthState.FAILED),
            generation=3,
            owner_lease=OwnerLease(owner_id="cli", generation=3),
        )
    )
    observations = iter(
        (
            _health(authority=RuntimeHealthState.FAILED),
            _health(authority=RuntimeHealthState.FAILED),
            _health(),
            _health(),
        )
    )
    live_core = False
    host = AuthorityHost(process=Process(7114))

    def start_core(healthy: Callable[[], bool]) -> ServiceLifecycleResult:
        nonlocal live_core
        ready = healthy()
        live_core = True
        return (
            ServiceLifecycleResult(status="started", pid=7113)
            if ready
            else ServiceLifecycleResult(status="failed")
        )

    supervisor = _supervisor(
        record=record,
        health_probe=lambda: next(observations),
        start_core=start_core,
        authority_host=host,
        owns_pid_record=lambda: live_core,
    )

    result = supervisor.start(owner_id="desktop-recovered")

    assert result.status == "started"
    assert record.read().owner_lease is not None
    assert record.read().owner_lease.owner_id == "desktop-recovered"


def test_start_cancellation_does_not_promote_a_stopping_claim() -> None:
    record = MemoryRecord()

    def cancel_before_core_finishes(
        healthy: Callable[[], bool],
    ) -> ServiceLifecycleResult:
        current = record.read()
        record.write(replace(current, state=RuntimeHealthState.STOPPING))
        return ServiceLifecycleResult(status="started", pid=7110)

    supervisor = _supervisor(
        record=record,
        start_core=cancel_before_core_finishes,
        stop_core=lambda: ServiceLifecycleResult(status="stopped", pid=7110),
    )

    result = supervisor.start(owner_id="desktop-cancelled")

    assert result.status == "failed"
    assert record.read().state is RuntimeHealthState.STOPPING
    assert record.read().startup_owner_id == "desktop-cancelled"


def test_authority_launch_race_reaps_process_after_start_claim_is_cancelled() -> None:
    record = MemoryRecord()
    calls: list[str] = []

    class CancellingAuthorityHost(AuthorityHost):
        def start(self) -> Optional[AuthorityProcess]:
            calls.append("authority")
            record.write(replace(record.read(), state=RuntimeHealthState.STOPPING))
            return Process(7112)

    supervisor = _supervisor(
        record=record,
        start_core=lambda healthy: (
            healthy() and ServiceLifecycleResult(status="started", pid=7113)
        ),
        stop_core=lambda: (
            calls.append("stop-core") or ServiceLifecycleResult(status="stopped")
        ),
        authority_host=CancellingAuthorityHost(calls=calls),
    )

    result = supervisor.start(owner_id="desktop-race")

    assert result.status == "failed"
    assert calls == ["authority", "stop-authority:7112", "stop-core"]


def test_start_rejects_failed_authority_health() -> None:
    supervisor = _supervisor(
        health_probe=lambda: _health(authority=RuntimeHealthState.FAILED),
        start_core=lambda healthy: ServiceLifecycleResult(status="failed", pid=7102),
    )

    result = supervisor.start(owner_id="cli")

    assert result.status == "failed"
    assert supervisor.status().state is RuntimeHealthState.FAILED


def test_stop_clears_owned_record() -> None:
    record = MemoryRecord()
    supervisor = _supervisor(record=record)
    supervisor.start(owner_id="cli")

    result = supervisor.stop()

    assert result.status == "stopped"
    assert record.read().state is RuntimeHealthState.STOPPED


def test_existing_runtime_without_record_becomes_generation_one() -> None:
    supervisor = _supervisor(
        start_core=lambda healthy: ServiceLifecycleResult(
            status="already_running", pid=7104
        )
    )

    result = supervisor.start(owner_id="cli")

    assert result.status == "already_running"
    assert supervisor.status().generation == 1


def test_start_launches_authority_after_core() -> None:
    observations = iter(
        (
            _health(authority=RuntimeHealthState.FAILED),
            _health(authority=RuntimeHealthState.FAILED),
            _health(),
            _health(),
            _health(),
        )
    )
    calls: list[str] = []
    host = AuthorityHost(process=Process(7105), calls=calls)
    supervisor = _supervisor(
        health_probe=lambda: next(observations),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7104))
        ),
        authority_host=host,
    )

    result = supervisor.start(owner_id="cli")

    assert result.status == "started"
    assert calls == ["core", "authority"]
    assert supervisor.status().component(RuntimeComponent.GODOT_AUTHORITY).pid == 7105


def test_authority_launch_failure_stops_core() -> None:
    calls: list[str] = []
    host = AuthorityHost(process=None, calls=calls)
    supervisor = _supervisor(
        health_probe=lambda: _health(authority=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7106))
        ),
        stop_core=lambda: (
            calls.append("stop-core")
            or ServiceLifecycleResult(status="stopped", pid=7106)
        ),
        authority_host=host,
    )

    result = supervisor.start(owner_id="cli")

    assert result.status == "failed"
    assert isinstance(result.error, LaunchFailedError)
    assert calls == ["core", "authority", "stop-core"]


def test_typed_authority_error_is_preserved() -> None:
    calls: list[str] = []
    host = AuthorityHost(
        failure=AuthorityHostError("missing Linux Dedicated authority"), calls=calls
    )
    supervisor = _supervisor(
        health_probe=lambda: _health(authority=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7108))
        ),
        stop_core=lambda: (
            calls.append("stop-core")
            or ServiceLifecycleResult(status="stopped", pid=7108)
        ),
        authority_host=host,
    )

    result = supervisor.start(owner_id="cli")

    assert isinstance(result.error, LaunchFailedError)
    assert "missing Linux Dedicated authority" in str(result.error)
    assert calls == ["core", "authority", "stop-core"]


def test_authority_timeout_stops_authority_before_core() -> None:
    clock = FakeClock()
    calls: list[str] = []
    host = AuthorityHost(process=Process(7107), calls=calls)
    supervisor = _supervisor(
        health_probe=lambda: _health(authority=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7106))
        ),
        stop_core=lambda: (
            calls.append("stop-core")
            or ServiceLifecycleResult(status="stopped", pid=7106)
        ),
        authority_host=host,
        authority_timeout_seconds=0.2,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    result = supervisor.start(owner_id="cli")

    assert result.status == "failed"
    assert calls == ["core", "authority", "stop-authority:7107", "stop-core"]


def test_new_invocation_stops_recorded_authority_pid() -> None:
    record = MemoryRecord()
    first_host = AuthorityHost(process=Process(7109))
    first = _supervisor(record=record, authority_host=first_host)
    first.start(owner_id="cli")
    stopped: list[str] = []
    second_host = AuthorityHost(calls=stopped)
    second = _supervisor(
        record=record,
        authority_host=second_host,
        stop_core=lambda: (
            stopped.append("core") or ServiceLifecycleResult(status="stopped")
        ),
    )

    result = second.stop()

    assert result.status == "stopped"
    assert stopped == ["stop-authority:7109", "core"]


def test_repeated_start_preserves_generation_without_second_authority() -> None:
    record = MemoryRecord()
    first = _supervisor(
        record=record,
        authority_host=AuthorityHost(process=Process(7110)),
    )
    first.start(owner_id="cli")
    second_calls: list[str] = []
    second = _supervisor(
        record=record,
        start_core=lambda healthy: ServiceLifecycleResult(
            status="already_running", pid=7111
        ),
        authority_host=AuthorityHost(process=None, calls=second_calls),
    )

    result = second.start(owner_id="cli")

    assert result.status == "already_running"
    assert second_calls == []
    assert record.read().generation == 1
    assert record.read().component(RuntimeComponent.GODOT_AUTHORITY).pid == 7110
