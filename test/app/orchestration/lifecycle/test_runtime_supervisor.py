from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Optional

from app.orchestration.lifecycle.ports import AuthorityProcess
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ComponentSnapshot,
    ComponentState,
    FailureSnapshot,
    ModelHealthProjection,
    ModelOverallState,
    OwnerLease,
    RuntimeComponent,
    RuntimeObservation,
    RuntimePhase,
    RuntimeProgressPhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
)
from app.orchestration.lifecycle.runtime_supervisor import RuntimeSupervisor
from app.orchestration.lifecycle.types import (
    AuthorityHostError,
    LifecycleBusyError,
    LifecycleCancelledError,
    ServiceLifecycleResult,
)
from test.app.orchestration.lifecycle.service_fakes import FakeClock


def _observation(
    *,
    authority: ComponentState = ComponentState.READY,
    model: ModelOverallState = ModelOverallState.READY,
) -> RuntimeObservation:
    return RuntimeObservation(
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, ComponentState.READY),
            ComponentSnapshot(RuntimeComponent.GATEWAY, ComponentState.READY),
            ComponentSnapshot(RuntimeComponent.GODOT_AUTHORITY, authority),
            ComponentSnapshot(
                RuntimeComponent.OLLAMA,
                ComponentState.READY
                if model is ModelOverallState.READY
                else ComponentState.DEGRADED,
            ),
        ),
        model_state=model,
    )


class MemoryRecord:
    def __init__(self) -> None:
        self.value = RuntimeSnapshotV1(instance_id="memory-instance")
        self.history: list[RuntimeSnapshotV1] = []

    def read(self) -> RuntimeSnapshotV1:
        return self.value

    def initialize_if_fresh(self) -> RuntimeSnapshotV1:
        return self.value

    def write(self, snapshot: RuntimeSnapshotV1) -> None:
        self.history.append(snapshot)
        self.value = snapshot


@dataclass
class Process:
    pid: int


@dataclass
class ExitedProcess:
    pid: int
    exit_code: int = 1

    def poll(self) -> int:
        return self.exit_code


class AuthorityHost:
    def __init__(
        self,
        *,
        process: Optional[AuthorityProcess] = None,
        failure: Optional[AuthorityHostError] = None,
        stop_failure: Optional[RuntimeError] = None,
        calls: Optional[list[str]] = None,
    ) -> None:
        self.process = process
        self.failure = failure
        self.stop_failure = stop_failure
        self.calls = calls if calls is not None else []

    def start(self) -> Optional[AuthorityProcess]:
        self.calls.append("authority")
        if self.failure is not None:
            raise self.failure
        return self.process

    def stop(self, process: AuthorityProcess) -> None:
        self.calls.append(f"stop-authority:{process.pid}")
        if self.stop_failure is not None:
            raise self.stop_failure


def _supervisor(
    *,
    record: Optional[MemoryRecord] = None,
    health_probe: Callable[[], RuntimeObservation] = _observation,
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


def test_start_persists_core_then_world_as_one_generation() -> None:
    phases: list[RuntimeProgressPhase] = []
    supervisor = _supervisor(
        authority_host=AuthorityHost(process=Process(7105)),
        progress_callback=phases.append,
        start_core=lambda healthy: (
            healthy() and ServiceLifecycleResult(status="started", pid=7101)
        ),
    )

    result = supervisor.start(owner_id="cli", wait_target=RuntimeTarget.WORLD)

    assert result.status == "started"
    assert result.operation_id
    assert result.generation == 1
    projection = supervisor.status()
    assert projection.tier is BackendTier.WORLD_READY
    assert projection.generation == 1
    assert projection.owner_lease == OwnerLease("cli", 1)
    assert projection.subphase == ""
    assert projection.component(RuntimeComponent.CORE).pid == 7101
    assert projection.component(RuntimeComponent.GATEWAY).pid == 7101
    assert {item.phase for item in projection.timings} == {"core", "world"}
    assert phases[:3] == [
        RuntimeProgressPhase.STARTING,
        RuntimeProgressPhase.CORE_READY,
        RuntimeProgressPhase.AUTHORITY_STARTING,
    ]
    assert phases[-1] is RuntimeProgressPhase.WORLD_READY


def test_core_wait_target_does_not_start_world() -> None:
    calls: list[str] = []
    host = AuthorityHost(process=Process(7105), calls=calls)
    supervisor = _supervisor(
        authority_host=host,
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7101))
        ),
    )

    result = supervisor.start(
        owner_id="setup",
        desired_target=RuntimeTarget.CORE,
        wait_target=RuntimeTarget.CORE,
    )

    assert result.status == "started"
    assert calls == ["core"]
    assert supervisor.status().tier is BackendTier.CORE_READY


def test_start_cancellation_cleans_up_before_core_launch() -> None:
    record = MemoryRecord()
    calls: list[str] = []
    supervisor = _supervisor(
        record=record,
        start_core=lambda healthy: (
            calls.append("core") or ServiceLifecycleResult(status="started")
        ),
        stop_core=lambda: (
            calls.append("stop") or ServiceLifecycleResult(status="already_stopped")
        ),
    )

    result = supervisor.start(owner_id="desktop", cancel_check=lambda: True)

    assert result.status == "failed"
    assert isinstance(result.error, LifecycleCancelledError)
    assert calls == ["stop"]
    assert record.value.tier is BackendTier.OFFLINE
    assert record.value.phase is RuntimePhase.FAILED
    assert record.value.failures[0].code == "START_CANCELLED"


def test_start_cancellation_observed_by_core_health_checkpoint() -> None:
    record = MemoryRecord()
    calls: list[str] = []

    def start_core(healthy: Callable[[], bool]) -> ServiceLifecycleResult:
        calls.append("core")
        record.write(replace(record.read(), phase=RuntimePhase.QUIESCING, revision=1))
        healthy()
        return ServiceLifecycleResult(status="started")

    supervisor = _supervisor(
        record=record,
        start_core=start_core,
        stop_core=lambda: (
            calls.append("stop") or ServiceLifecycleResult(status="already_stopped")
        ),
    )

    result = supervisor.start(owner_id="desktop")

    assert result.status == "failed"
    assert isinstance(result.error, LifecycleCancelledError)
    assert calls == ["core", "stop"]


def test_world_wait_can_attach_to_core_resident_convergence() -> None:
    record = MemoryRecord()
    world_published = False

    def sleeper(_seconds: float) -> None:
        nonlocal world_published
        if world_published:
            return
        world_published = True
        current = record.read()
        record.write(
            replace(
                current,
                revision=current.revision + 1,
                tier=BackendTier.WORLD_READY,
                phase=RuntimePhase.WORLD_READY,
                reached_target=RuntimeTarget.WORLD,
                components=(
                    *current.components,
                    ComponentSnapshot(
                        RuntimeComponent.GODOT_AUTHORITY,
                        ComponentState.READY,
                        pid=7105,
                    ),
                ),
            )
        )

    supervisor = _supervisor(
        record=record,
        authority_host=None,
        sleeper=sleeper,
    )

    result = supervisor.start(
        owner_id="cli",
        wait_target=RuntimeTarget.WORLD,
    )

    assert result.status == "started"
    assert supervisor.status().tier is BackendTier.WORLD_READY


def test_normal_wait_requires_model_projection_after_world_ready() -> None:
    record = MemoryRecord()
    model_states = [
        ModelHealthProjection(
            state=ModelOverallState.DEGRADED,
            common_state=ModelOverallState.READY,
            emergency_state=ModelOverallState.READY,
        ),
        ModelHealthProjection(
            state=ModelOverallState.READY,
            common_state=ModelOverallState.READY,
            emergency_state=ModelOverallState.READY,
            revision=3,
        ),
    ]
    model_index = 0

    def model_probe() -> ModelHealthProjection:
        nonlocal model_index
        value = model_states[min(model_index, len(model_states) - 1)]
        model_index += 1
        return value

    published = False

    def sleeper(_seconds: float) -> None:
        nonlocal published
        if published:
            return
        published = True
        current = record.read()
        record.write(
            replace(
                current,
                revision=current.revision + 1,
                tier=BackendTier.WORLD_READY,
                phase=RuntimePhase.WORLD_READY,
                reached_target=RuntimeTarget.WORLD,
                components=(
                    *current.components,
                    ComponentSnapshot(
                        RuntimeComponent.GODOT_AUTHORITY,
                        ComponentState.READY,
                        pid=7105,
                    ),
                ),
            )
        )

    supervisor = _supervisor(
        record=record,
        authority_host=None,
        authority_timeout_seconds=1.0,
        sleeper=sleeper,
        model_projection_probe=model_probe,
    )

    result = supervisor.start(
        owner_id="cli",
        desired_target=RuntimeTarget.NORMAL,
        wait_target=RuntimeTarget.NORMAL,
    )

    assert result.status == "started"
    assert supervisor.status().tier is BackendTier.WORLD_READY


def test_normal_wait_timeout_keeps_world_ready_core_running() -> None:
    record = MemoryRecord()
    clock = FakeClock()
    published = False

    def sleeper(_seconds: float) -> None:
        nonlocal published
        clock.sleep(_seconds)
        if published:
            return
        published = True
        current = record.read()
        record.write(
            replace(
                current,
                revision=current.revision + 1,
                tier=BackendTier.WORLD_READY,
                phase=RuntimePhase.WORLD_READY,
                reached_target=RuntimeTarget.WORLD,
                components=(
                    *current.components,
                    ComponentSnapshot(
                        RuntimeComponent.GODOT_AUTHORITY,
                        ComponentState.READY,
                        pid=7105,
                    ),
                ),
            )
        )

    supervisor = _supervisor(
        record=record,
        authority_host=None,
        authority_timeout_seconds=0.2,
        monotonic=clock.monotonic,
        sleeper=sleeper,
        model_projection_probe=lambda: ModelHealthProjection(
            state=ModelOverallState.DEGRADED,
            common_state=ModelOverallState.READY,
            emergency_state=ModelOverallState.READY,
        ),
    )

    result = supervisor.start(
        owner_id="cli",
        desired_target=RuntimeTarget.NORMAL,
        wait_target=RuntimeTarget.NORMAL,
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "model" in str(result.error).lower()
    assert supervisor.status().tier is BackendTier.WORLD_READY


def test_repeated_start_attaches_and_only_raises_desired_target() -> None:
    record = MemoryRecord()
    calls: list[str] = []
    supervisor = _supervisor(
        record=record,
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7101))
        ),
    )

    assert (
        supervisor.start(owner_id="cli", desired_target=RuntimeTarget.CORE).status
        == "started"
    )
    result = supervisor.start(owner_id="desktop", desired_target=RuntimeTarget.NORMAL)

    assert result.status == "already_running"
    assert calls == ["core"]
    assert supervisor.status().desired_target is RuntimeTarget.NORMAL
    assert supervisor.status().owner_lease == OwnerLease("cli", 1)


def test_repeated_start_waits_for_escalated_world_target() -> None:
    record = MemoryRecord()
    published = False

    def sleeper(_seconds: float) -> None:
        nonlocal published
        if published:
            return
        published = True
        current = record.read()
        record.write(
            replace(
                current,
                revision=current.revision + 1,
                tier=BackendTier.WORLD_READY,
                phase=RuntimePhase.WORLD_READY,
                reached_target=RuntimeTarget.WORLD,
            )
        )

    supervisor = _supervisor(
        record=record,
        sleeper=sleeper,
        authority_timeout_seconds=1.0,
    )
    assert (
        supervisor.start(
            owner_id="cli",
            desired_target=RuntimeTarget.CORE,
            wait_target=RuntimeTarget.CORE,
        ).status
        == "started"
    )

    result = supervisor.start(
        owner_id="desktop",
        desired_target=RuntimeTarget.WORLD,
        wait_target=RuntimeTarget.WORLD,
    )

    assert result.status == "already_running"
    assert result.generation == 1
    assert supervisor.status().tier is BackendTier.WORLD_READY
    assert supervisor.status().desired_target is RuntimeTarget.WORLD


def test_start_during_shutdown_returns_busy_without_raising_target() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.QUIESCING,
        desired_target=RuntimeTarget.NORMAL,
        owner_lease=OwnerLease("cli", 1),
    )
    calls: list[str] = []
    supervisor = _supervisor(
        record=record,
        start_core=lambda healthy: (
            calls.append("core") or ServiceLifecycleResult(status="started")
        ),
        owns_pid_record=lambda: True,
    )

    result = supervisor.start(owner_id="desktop", desired_target=RuntimeTarget.NORMAL)

    assert result.status == "failed"
    assert result.error is not None
    assert "wait for OFFLINE" in str(result.error)
    assert calls == []
    assert supervisor.status().phase is RuntimePhase.QUIESCING


def test_start_rejects_a_runtime_already_claimed_by_another_startup() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        phase=RuntimePhase.CORE_STARTING,
        startup_owner_id="desktop-existing",
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


def test_stale_generation_is_reconciled_without_deleting_history() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        generation=3,
        revision=4,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        owner_lease=OwnerLease("old", 3),
    )
    supervisor = _supervisor(
        record=record,
        owns_pid_record=lambda: False,
        start_core=lambda healthy: (
            healthy() and ServiceLifecycleResult(status="started", pid=7101)
        ),
    )

    result = supervisor.start(owner_id="new", desired_target=RuntimeTarget.CORE)

    assert result.status == "started"
    assert supervisor.status().generation == 4
    assert supervisor.status().revision > 4


def test_world_failure_keeps_core_ready_and_does_not_stop_core() -> None:
    clock = FakeClock()
    calls: list[str] = []
    supervisor = _supervisor(
        health_probe=lambda: _observation(authority=ComponentState.FAILED),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7101))
        ),
        stop_core=lambda: (
            calls.append("stop-core") or ServiceLifecycleResult(status="stopped")
        ),
        authority_host=AuthorityHost(process=Process(7105), calls=calls),
        authority_timeout_seconds=0.2,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    result = supervisor.start(owner_id="cli", wait_target=RuntimeTarget.WORLD)

    assert result.status == "failed"
    assert "stop-core" not in calls
    assert supervisor.status().tier is BackendTier.CORE_READY
    assert supervisor.status().phase is RuntimePhase.FAILED


def test_stop_retains_offline_snapshot_and_generation() -> None:
    record = MemoryRecord()
    supervisor = _supervisor(record=record)
    supervisor.start(owner_id="cli", desired_target=RuntimeTarget.CORE)
    before = supervisor.status()

    result = supervisor.stop()

    assert result.status == "stopped"
    after = supervisor.status()
    assert after.tier is BackendTier.OFFLINE
    assert after.generation == before.generation
    assert after.revision > before.revision


def test_stop_is_idempotent_after_writer_handoff_was_revoked() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        tier=BackendTier.OFFLINE,
        phase=RuntimePhase.OFFLINE,
        writer_credential_digest=None,
    )
    supervisor = _supervisor(record=record)

    result = supervisor.stop()

    assert result.status == "already_stopped"
    assert record.history == []


def test_stop_rejects_a_second_shutdown_while_core_is_still_present() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        generation=3,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_STOPPING,
        owner_lease=OwnerLease("cli", 3),
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, ComponentState.READY, pid=7101),
        ),
    )
    calls: list[str] = []
    supervisor = _supervisor(
        record=record,
        owns_pid_record=lambda: True,
        stop_core=lambda: (
            calls.append("stop-core") or ServiceLifecycleResult(status="stopped")
        ),
    )

    result = supervisor.stop()

    assert result.status == "failed"
    assert isinstance(result.error, LifecycleBusyError)
    assert calls == []
    assert record.read().phase is RuntimePhase.CORE_STOPPING


def test_stop_recovers_recorded_world_with_a_parent_recovery_host() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        generation=4,
        tier=BackendTier.WORLD_READY,
        phase=RuntimePhase.WORLD_READY,
        desired_target=RuntimeTarget.NORMAL,
        reached_target=RuntimeTarget.WORLD,
        owner_lease=OwnerLease("cli", 4),
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, ComponentState.READY, pid=7101),
            ComponentSnapshot(RuntimeComponent.GATEWAY, ComponentState.READY, pid=7101),
            ComponentSnapshot(
                RuntimeComponent.GODOT_AUTHORITY,
                ComponentState.READY,
                pid=7105,
            ),
        ),
    )
    recovery_host = AuthorityHost(process=Process(7105))
    supervisor = _supervisor(
        record=record,
        authority_recovery_host=recovery_host,
        owns_pid_record=lambda: True,
    )

    result = supervisor.stop()

    assert result.status == "stopped"
    assert recovery_host.calls == ["stop-authority:7105"]
    assert supervisor.status().tier is BackendTier.OFFLINE


def test_interrupted_stop_reconciles_after_core_disappears() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        generation=5,
        tier=BackendTier.WORLD_READY,
        phase=RuntimePhase.CORE_STOPPING,
        owner_lease=OwnerLease("cli", 5),
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, ComponentState.READY, pid=7101),
            ComponentSnapshot(
                RuntimeComponent.GODOT_AUTHORITY,
                ComponentState.READY,
                pid=7105,
            ),
        ),
    )
    calls: list[str] = []
    recovery_host = AuthorityHost(process=Process(7105), calls=calls)
    supervisor = _supervisor(
        record=record,
        authority_recovery_host=recovery_host,
        owns_pid_record=lambda: False,
        stop_core=lambda: (
            calls.append("stop-core")
            or ServiceLifecycleResult(status="already_stopped")
        ),
    )

    result = supervisor.stop()

    assert result.status == "already_stopped"
    assert calls == ["stop-authority:7105", "stop-core"]
    assert supervisor.status().tier is BackendTier.OFFLINE


def test_stop_does_not_hide_a_world_cleanup_failure() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        generation=6,
        tier=BackendTier.WORLD_READY,
        phase=RuntimePhase.WORLD_READY,
        owner_lease=OwnerLease("cli", 6),
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, ComponentState.READY, pid=7101),
            ComponentSnapshot(
                RuntimeComponent.GODOT_AUTHORITY,
                ComponentState.FAILED,
                detail="Godot process ignored stop",
                pid=7105,
            ),
        ),
        failures=(
            FailureSnapshot(
                "WORLD_STOP_INCOMPLETE",
                "Godot process ignored stop",
                "world_stop",
            ),
        ),
    )
    supervisor = _supervisor(
        record=record,
        authority_recovery_host=AuthorityHost(process=Process(7105)),
        owns_pid_record=lambda: True,
    )

    result = supervisor.stop()

    assert result.status == "failed"
    assert "World cleanup incomplete" in str(result.error)
    assert record.read().phase is RuntimePhase.FAILED


def test_start_refuses_a_new_generation_after_incomplete_shutdown() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        generation=7,
        tier=BackendTier.WORLD_READY,
        phase=RuntimePhase.FAILED,
        owner_lease=OwnerLease("cli", 7),
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, ComponentState.READY, pid=7101),
            ComponentSnapshot(
                RuntimeComponent.GODOT_AUTHORITY,
                ComponentState.FAILED,
                detail="Godot process ignored stop",
                pid=7105,
            ),
        ),
        failures=(
            FailureSnapshot(
                "STOP_INCOMPLETE",
                "Godot process ignored stop",
                "stop",
            ),
        ),
    )
    calls: list[str] = []
    supervisor = _supervisor(
        record=record,
        owns_pid_record=lambda: False,
        start_core=lambda _healthy: (
            calls.append("start-core") or ServiceLifecycleResult(status="started")
        ),
    )

    result = supervisor.start(owner_id="next")

    assert result.status == "failed"
    assert "retry stop" in str(result.error)
    assert calls == []
    assert record.read().generation == 7


def test_status_projects_latest_model_evidence_without_rewriting_snapshot() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        owner_lease=OwnerLease("cli", 1),
        model_state=ModelOverallState.DEGRADED,
    )
    supervisor = _supervisor(
        record=record,
        model_projection_probe=lambda: ModelHealthProjection(
            state=ModelOverallState.READY,
            common_state=ModelOverallState.READY,
            emergency_state=ModelOverallState.READY,
            revision=7,
        ),
    )

    projection = supervisor.status()

    assert projection.model_state is ModelOverallState.READY
    assert projection.model_revision == 7
    assert record.read().model_state is ModelOverallState.DEGRADED


def test_status_projects_offline_when_the_recorded_core_process_is_gone() -> None:
    record = MemoryRecord()
    record.value = replace(
        record.value,
        tier=BackendTier.WORLD_READY,
        phase=RuntimePhase.WORLD_READY,
        owner_lease=OwnerLease("cli", 1),
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, ComponentState.READY, pid=7101),
            ComponentSnapshot(RuntimeComponent.GATEWAY, ComponentState.READY, pid=7101),
        ),
    )
    supervisor = _supervisor(record=record, owns_pid_record=lambda: False)

    projection = supervisor.status()

    assert projection.tier is BackendTier.OFFLINE
    assert projection.phase is RuntimePhase.FAILED
    assert projection.subphase == "core_missing"
    assert projection.failures[0].code == "CORE_NOT_RUNNING"
    assert record.read().tier is BackendTier.WORLD_READY


def test_stop_publishes_reverse_ownership_phases_before_shutdown() -> None:
    record = MemoryRecord()
    supervisor = _supervisor(record=record)
    assert (
        supervisor.start(owner_id="cli", desired_target=RuntimeTarget.CORE).status
        == "started"
    )

    result = supervisor.stop()

    assert result.status == "stopped"
    phases = [item.phase for item in record.history]
    first_stop = phases.index(RuntimePhase.QUIESCING)
    assert phases[first_stop:] == [
        RuntimePhase.QUIESCING,
        RuntimePhase.WORLD_STOPPING,
        RuntimePhase.MODEL_LEASE_RELEASING,
        RuntimePhase.CORE_STOPPING,
        RuntimePhase.OFFLINE,
    ]


def test_stop_continues_core_shutdown_when_authority_stop_fails() -> None:
    calls: list[str] = []
    supervisor = _supervisor(
        authority_host=AuthorityHost(
            process=Process(7105),
            stop_failure=RuntimeError("authority is unresponsive"),
            calls=calls,
        ),
        stop_core=lambda: (
            calls.append("stop-core") or ServiceLifecycleResult(status="stopped")
        ),
    )
    assert (
        supervisor.start(owner_id="cli", wait_target=RuntimeTarget.WORLD).status
        == "started"
    )

    result = supervisor.stop()

    assert result.status == "failed"
    assert calls[-1] == "stop-core"
    assert supervisor.status().phase is RuntimePhase.FAILED
    assert supervisor.status().failures[0].code == "STOP_INCOMPLETE"


def test_lifecycle_pressure_gate_runs_warm_and_cold_cycles() -> None:
    """Keep the release reliability counts as a cheap, repeatable regression gate."""
    record = MemoryRecord()
    core_starts = 0
    core_stops = 0

    def start_core(healthy: Callable[[], bool]) -> ServiceLifecycleResult:
        nonlocal core_starts
        core_starts += 1
        assert healthy()
        return ServiceLifecycleResult(status="started", pid=7101)

    def stop_core() -> ServiceLifecycleResult:
        nonlocal core_stops
        core_stops += 1
        return ServiceLifecycleResult(status="stopped", pid=7101)

    supervisor = _supervisor(
        record=record,
        start_core=start_core,
        stop_core=stop_core,
    )

    # Warm attach must never create a second Core generation or launch.
    assert (
        supervisor.start(owner_id="cli", desired_target=RuntimeTarget.CORE).status
        == "started"
    )
    for _ in range(300):
        result = supervisor.start(owner_id="desktop", desired_target=RuntimeTarget.CORE)
        assert result.status == "already_running"
        assert result.generation == 1
        assert supervisor.status().tier is BackendTier.CORE_READY

    # Cold cycles must fully publish OFFLINE before the next generation starts.
    for expected_generation in range(2, 52):
        stopped = supervisor.stop()
        assert stopped.status == "stopped"
        assert supervisor.status().tier is BackendTier.OFFLINE

        started = supervisor.start(owner_id="cli", desired_target=RuntimeTarget.CORE)
        assert started.status == "started"
        assert started.generation == expected_generation
        assert supervisor.status().tier is BackendTier.CORE_READY

    assert core_starts == 51
    assert core_stops == 50
