"""Core/World lifecycle coordinator backed by RuntimeSnapshotV1."""

from __future__ import annotations

import time
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from typing import Callable, Iterator, Optional

from app.orchestration.lifecycle.ports import (
    AuthorityHostPort,
    AuthorityProcess,
    LifecycleLease,
    RecordedAuthorityProcess,
    RuntimeRecordPort,
)
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ComponentSnapshot,
    ComponentState,
    FailureSnapshot,
    ModelHealthProjection,
    OwnerLease,
    RuntimeComponent,
    RuntimeObservation,
    RuntimePhase,
    RuntimeProgressPhase,
    RuntimeProjectionV1,
    RuntimeSnapshotV1,
    RuntimeTarget,
    TimingSnapshot,
)
from app.orchestration.lifecycle.types import (
    AuthorityHostError,
    LaunchFailedError,
    LifecycleBusyError,
    ServiceLifecycleResult,
    SnapshotRecoveryRequiredError,
)

ObservationProbe = Callable[[], RuntimeObservation]
StartCore = Callable[[Callable[[], bool]], ServiceLifecycleResult]
StopCore = Callable[[], ServiceLifecycleResult]
OwnedRecord = Callable[[], bool]
ProgressCallback = Callable[[RuntimeProgressPhase], None]
CommandLeaseFactory = Callable[[], LifecycleLease]
ModelProjectionProbe = Callable[[], ModelHealthProjection]


class RuntimeSupervisor:
    """Coordinate one generation without a second durable lifecycle fact source.

    The normal entrypoint waits only for Core.  A Core-resident worker owns
    World convergence after that handoff; callers that explicitly request a
    World wait still use the bounded synchronous path.
    """

    def __init__(
        self,
        *,
        runtime_record: RuntimeRecordPort,
        health_probe: ObservationProbe,
        start_core: StartCore,
        stop_core: StopCore,
        owns_pid_record: OwnedRecord = lambda: True,
        authority_host: Optional[AuthorityHostPort] = None,
        authority_timeout_seconds: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        progress_callback: Optional[ProgressCallback] = None,
        command_lease_factory: Optional[CommandLeaseFactory] = None,
        model_projection_probe: Optional[ModelProjectionProbe] = None,
    ) -> None:
        self._runtime_record = runtime_record
        self._health_probe = health_probe
        self._start_core = start_core
        self._stop_core = stop_core
        self._owns_pid_record = owns_pid_record
        self._authority_host = authority_host
        self._authority_timeout_seconds = authority_timeout_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._progress_callback = progress_callback
        self._command_lease_factory = command_lease_factory
        self._model_projection_probe = model_projection_probe
        self._authority_process: Optional[AuthorityProcess] = None
        self._start_started_at: Optional[float] = None
        self._world_started_at: Optional[float] = None

    def start(
        self,
        *,
        owner_id: str,
        desired_target: RuntimeTarget = RuntimeTarget.NORMAL,
        wait_target: RuntimeTarget = RuntimeTarget.CORE,
        correlation_id: Optional[str] = None,
    ) -> ServiceLifecycleResult:
        """Reserve one generation, reach Core, then converge World safely."""
        try:
            record_before_start = self._initialize_and_read()
        except SnapshotRecoveryRequiredError as error:
            return ServiceLifecycleResult(status="failed", error=LaunchFailedError(str(error)))

        with self._command_lock():
            record_before_start = self._runtime_record.read()
            if record_before_start.phase is RuntimePhase.RECOVERY_REQUIRED:
                return ServiceLifecycleResult(
                    status="failed",
                    error=LaunchFailedError(self._recovery_detail(record_before_start)),
                )
            if record_before_start.startup_owner_id is not None:
                if record_before_start.startup_owner_id == owner_id:
                    return ServiceLifecycleResult(
                        status="failed",
                        error=LifecycleBusyError("Runtime startup is already owned by this command"),
                    )
                return ServiceLifecycleResult(
                    status="failed",
                    error=LifecycleBusyError("Runtime startup is already owned by another command"),
                )
            if record_before_start.phase in {
                RuntimePhase.QUIESCING,
                RuntimePhase.WORLD_STOPPING,
                RuntimePhase.MODEL_LEASE_RELEASING,
                RuntimePhase.CORE_STOPPING,
            }:
                return ServiceLifecycleResult(
                    status="failed",
                    error=LifecycleBusyError("Runtime is stopping; wait for OFFLINE before starting again"),
                )
            if record_before_start.owner_lease is not None and record_before_start.tier is not BackendTier.OFFLINE:
                if self._owns_pid_record():
                    requested = max(
                        record_before_start.desired_target,
                        desired_target,
                        key=lambda target: target.rank,
                    )
                    updated = replace(
                        record_before_start,
                        revision=record_before_start.revision + 1,
                        desired_target=requested,
                    )
                    self._runtime_record.write(updated)
                    return ServiceLifecycleResult(status="already_running")
                record_before_start = self._offline_snapshot(
                    record_before_start,
                    phase=RuntimePhase.PREFLIGHT,
                    detail="stale generation reconciled before restart",
                )
                self._runtime_record.write(record_before_start)

            generation = record_before_start.generation + 1
            starting = replace(
                record_before_start,
                revision=record_before_start.revision + 1,
                generation=generation,
                tier=BackendTier.OFFLINE,
                phase=RuntimePhase.CORE_STARTING,
                subphase="core",
                desired_target=desired_target,
                reached_target=None,
                components=(),
                endpoints=(),
                failures=(),
                correlation_id=correlation_id,
                owner_lease=None,
                startup_owner_id=owner_id,
            )
            self._runtime_record.write(starting)

        self._emit_progress(RuntimeProgressPhase.STARTING)
        self._start_started_at = self._monotonic()
        self._world_started_at = None

        def core_and_gateway_ready() -> bool:
            return self._health_probe().core_ready

        try:
            result = self._start_core(core_and_gateway_ready)
        except Exception as error:  # noqa: BLE001 - convert adapter failures to typed state
            return self._fail_start(owner_id, f"Core startup failed: {error}")
        if result.status not in {"started", "already_running"}:
            return self._fail_start(owner_id, str(result.error or "Core startup failed"))

        try:
            observation = self._health_probe()
        except Exception as error:  # noqa: BLE001 - startup must release its claim
            return self._fail_start(owner_id, f"Core readiness probe failed: {error}")
        if not observation.core_ready:
            return self._fail_start(owner_id, "Core did not publish CORE_READY")
        if not self._promote_core_ready(owner_id, observation, pid=result.pid):
            return self._fail_start(owner_id, "Runtime startup was cancelled before CORE_READY")
        self._emit_progress(RuntimeProgressPhase.CORE_READY)

        if (
            desired_target.rank >= RuntimeTarget.WORLD.rank
            and wait_target.rank >= RuntimeTarget.WORLD.rank
        ):
            if self._authority_host is not None:
                try:
                    self._start_authority(owner_id)
                except AuthorityHostError as error:
                    self._record_core_failure(owner_id, str(error))
                    self._emit_progress(RuntimeProgressPhase.FAILED)
                    return ServiceLifecycleResult(
                        status="failed", pid=result.pid, command=result.command, error=LaunchFailedError(str(error))
                    )
                if not self._wait_for_world(owner_id):
                    detail = self._authority_readiness_failure_detail()
                    self._record_core_failure(owner_id, detail)
                    self._emit_progress(RuntimeProgressPhase.FAILED)
                    return ServiceLifecycleResult(
                        status="failed", pid=result.pid, command=result.command, error=LaunchFailedError(detail)
                    )

        world_reached: Optional[bool] = False
        if (
            desired_target.rank >= RuntimeTarget.WORLD.rank
            and wait_target.rank >= RuntimeTarget.WORLD.rank
        ):
            world_reached = (
                self._promote_world_ready_if_available(owner_id)
                if self._authority_host is not None
                else self._wait_for_world_handoff(owner_id)
            )
            if world_reached is not True:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=result.pid,
                    command=result.command,
                    error=LaunchFailedError(
                        "Runtime startup was cancelled before World readiness completed"
                    ),
                )
        if world_reached:
            self._emit_progress(RuntimeProgressPhase.WORLD_READY)
        return result

    def stop(self) -> ServiceLifecycleResult:
        """Quiesce, release the owned authority and retain an OFFLINE snapshot."""
        with self._command_lock():
            record = self._runtime_record.read()
            if record.phase is RuntimePhase.RECOVERY_REQUIRED:
                return ServiceLifecycleResult(
                    status="failed",
                    error=LaunchFailedError(self._recovery_detail(record)),
                )
            if record.owner_lease is not None or record.startup_owner_id is not None:
                self._runtime_record.write(
                    replace(
                        record,
                        revision=record.revision + 1,
                        phase=RuntimePhase.QUIESCING,
                        subphase="stop_requested",
                        )
                    )
        self._emit_progress(RuntimeProgressPhase.STOPPING)
        stop_started_at = self._monotonic()
        self._transition_stop_phase(RuntimePhase.WORLD_STOPPING, "world")
        authority = self._authority_process or self._recorded_authority_process()
        authority_error: Optional[Exception] = None
        if authority is not None and self._authority_host is not None:
            try:
                self._authority_host.stop(authority)
            except Exception as error:  # noqa: BLE001 - preserve Core shutdown
                authority_error = error
        self._authority_process = None
        self._transition_stop_phase(RuntimePhase.MODEL_LEASE_RELEASING, "model")
        self._transition_stop_phase(RuntimePhase.CORE_STOPPING, "core")
        try:
            result = self._stop_core()
        except Exception as error:  # noqa: BLE001 - convert adapter failure
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"Core shutdown failed: {error}"),
            )
        if result.status in {"stopped", "already_stopped"} and authority_error is None:
            with self._command_lock():
                current = self._runtime_record.read()
                self._runtime_record.write(
                    replace(
                        current,
                        revision=current.revision + 1,
                        tier=BackendTier.OFFLINE,
                        phase=RuntimePhase.OFFLINE,
                        subphase="",
                        reached_target=None,
                        components=(),
                        endpoints=(),
                        owner_lease=None,
                        startup_owner_id=None,
                        failures=(),
                        timings=_append_timing(
                            current.timings,
                            "stop",
                            self._monotonic() - stop_started_at,
                        ),
                    )
                )
            return result

        detail_parts = []
        if authority_error is not None:
            detail_parts.append(f"Godot authority shutdown failed: {authority_error}")
        if result.status == "failed":
            detail_parts.append(str(result.error or "Core shutdown failed"))
        else:
            detail_parts.append("Core did not confirm shutdown")
        detail = "; ".join(detail_parts)
        self._record_stop_failure(detail)
        return ServiceLifecycleResult(
            status="failed",
            pid=result.pid,
            command=result.command,
            error=LaunchFailedError(detail),
        )

    def _transition_stop_phase(self, phase: RuntimePhase, subphase: str) -> None:
        """Publish the next bounded shutdown responsibility before doing it."""
        with self._command_lock():
            current = self._runtime_record.read()
            if current.phase is RuntimePhase.RECOVERY_REQUIRED:
                return
            if (
                current.tier is BackendTier.OFFLINE
                and current.owner_lease is None
                and current.startup_owner_id is None
            ):
                return
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    phase=phase,
                    subphase=subphase,
                )
            )

    def status(self) -> RuntimeProjectionV1:
        """Return a read-only projection; status never repairs or starts anything."""
        projection = self._runtime_record.read().projection()
        if self._model_projection_probe is None:
            return projection
        try:
            model = self._model_projection_probe()
        except (OSError, RuntimeError, ValueError):
            return projection
        return replace(
            projection,
            model_state=model.state,
            model_common_state=model.common_state,
            model_emergency_state=model.emergency_state,
            model_revision=model.revision,
        )

    def _initialize_and_read(self) -> RuntimeSnapshotV1:
        with self._command_lock():
            initializer = getattr(self._runtime_record, "initialize_if_fresh", None)
            if callable(initializer):
                return initializer()
            return self._runtime_record.read()

    @contextmanager
    def _command_lock(self) -> Iterator[None]:
        if self._command_lease_factory is None:
            with nullcontext():
                yield
            return
        lease = self._command_lease_factory()
        try:
            yield
        finally:
            lease.release()

    def _promote_core_ready(
        self,
        owner_id: str,
        observation: RuntimeObservation,
        *,
        pid: Optional[int] = None,
    ) -> bool:
        with self._command_lock():
            current = self._runtime_record.read()
            if current.startup_owner_id != owner_id:
                return False
            components = tuple(
                replace(item, pid=pid if pid is not None else item.pid)
                if item.component in {RuntimeComponent.CORE, RuntimeComponent.GATEWAY}
                else item
                for item in observation.components
            )
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    tier=BackendTier.CORE_READY,
                    phase=RuntimePhase.CORE_READY,
                    subphase="",
                    components=components,
                    endpoints=observation.endpoints,
                    model_state=observation.model_state,
                    model_common_state=observation.model_common_state,
                    model_emergency_state=observation.model_emergency_state,
                    model_revision=observation.model_revision,
                    failures=observation.failures,
                    timings=_append_timing(
                        (*current.timings, *observation.timings),
                        "core",
                        self._elapsed_since(self._start_started_at),
                    ),
                    protocol_versions=observation.protocol_versions,
                    owner_lease=OwnerLease(owner_id, current.generation),
                    startup_owner_id=None,
                    reached_target=RuntimeTarget.CORE,
                )
            )
        return True

    def _promote_world_ready_if_available(self, owner_id: str) -> Optional[bool]:
        observation = self._with_authority_evidence(self._health_probe())
        if not observation.world_ready:
            return False
        with self._command_lock():
            current = self._runtime_record.read()
            if current.owner_lease is None or current.owner_lease.owner_id != owner_id:
                return None
            components = tuple(
                replace(
                    item,
                    pid=(
                        item.pid
                        if item.pid is not None
                        else current.component(item.component).pid
                    ),
                )
                for item in observation.components
            )
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    tier=BackendTier.WORLD_READY,
                    phase=RuntimePhase.WORLD_READY,
                    subphase="",
                    components=components,
                    endpoints=observation.endpoints,
                    model_state=observation.model_state,
                    model_common_state=observation.model_common_state,
                    model_emergency_state=observation.model_emergency_state,
                    model_revision=observation.model_revision,
                    failures=observation.failures,
                    timings=_append_timing(
                        (*current.timings, *observation.timings),
                        "world",
                        self._elapsed_since(self._world_started_at),
                    ),
                    protocol_versions=observation.protocol_versions,
                    reached_target=RuntimeTarget.WORLD,
                )
            )
        return True

    def _start_authority(self, owner_id: str) -> None:
        if self._authority_host is None or self._authority_process is not None:
            return
        if not self._owner_matches(owner_id):
            raise AuthorityHostError("Runtime startup was cancelled")
        self._emit_progress(RuntimeProgressPhase.AUTHORITY_STARTING)
        self._world_started_at = self._monotonic()
        authority = self._authority_host.start()
        if authority is None:
            raise AuthorityHostError("Godot authority Runtime failed to start")
        if not self._startup_claim_matches(owner_id) and not self._owner_matches(owner_id):
            self._authority_host.stop(authority)
            raise AuthorityHostError("Runtime startup was cancelled")
        self._authority_process = authority
        with self._command_lock():
            current = self._runtime_record.read()
            if current.owner_lease is None or current.owner_lease.owner_id != owner_id:
                self._authority_host.stop(authority)
                self._authority_process = None
                raise AuthorityHostError("Runtime startup was cancelled")
            components = tuple(
                ComponentSnapshot(
                    component=item.component,
                    state=ComponentState.STARTING,
                    detail=item.detail,
                    pid=authority.pid,
                    executable=item.executable,
                    birth_identity=item.birth_identity,
                )
                if item.component is RuntimeComponent.GODOT_AUTHORITY
                else item
                for item in current.components
            )
            if not any(
                item.component is RuntimeComponent.GODOT_AUTHORITY
                for item in components
            ):
                components += (
                    ComponentSnapshot(
                        RuntimeComponent.GODOT_AUTHORITY,
                        ComponentState.STARTING,
                        pid=authority.pid,
                    ),
                )
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    phase=RuntimePhase.WORLD_STARTING,
                    subphase="authority_starting",
                    components=components,
                )
            )

    def _wait_for_world(self, owner_id: str) -> bool:
        deadline = self._monotonic() + self._authority_timeout_seconds
        while True:
            if not self._owner_matches(owner_id):
                return False
            authority_poll = getattr(self._authority_process, "poll", None)
            if callable(authority_poll) and authority_poll() is not None:
                return False
            if self._health_probe().world_ready:
                return True
            if self._monotonic() >= deadline:
                return False
            self._sleeper(0.1)

    def _wait_for_world_handoff(self, owner_id: str) -> Optional[bool]:
        """Wait for the Core-resident worker to publish WORLD_READY."""
        deadline = self._monotonic() + self._authority_timeout_seconds
        while True:
            current = self._runtime_record.read()
            if current.owner_lease is None or current.owner_lease.owner_id != owner_id:
                return None
            if current.tier is BackendTier.WORLD_READY:
                return True
            if current.phase in {
                RuntimePhase.FAILED,
                RuntimePhase.RECOVERY_REQUIRED,
                RuntimePhase.OFFLINE,
            }:
                return False
            if self._monotonic() >= deadline:
                return False
            self._sleeper(0.1)

    def _authority_readiness_failure_detail(self) -> str:
        authority_poll = getattr(self._authority_process, "poll", None)
        if callable(authority_poll):
            exit_code = authority_poll()
            if exit_code is not None:
                return f"Godot authority Runtime exited before readiness (exit code {exit_code})"
        return "Godot authority Runtime did not satisfy the readiness contract before timeout"

    def _recorded_authority_process(self) -> Optional[AuthorityProcess]:
        record = self._runtime_record.read()
        component = record.component(RuntimeComponent.GODOT_AUTHORITY)
        return RecordedAuthorityProcess(component.pid) if component.pid else None

    def _fail_start(self, owner_id: str, detail: str) -> ServiceLifecycleResult:
        cleanup_detail = self._stop_owned_resources()
        if cleanup_detail:
            detail = f"{detail}; cleanup incomplete: {cleanup_detail}"
        with self._command_lock():
            current = self._runtime_record.read()
            if current.startup_owner_id == owner_id:
                self._runtime_record.write(
                    replace(
                        current,
                        revision=current.revision + 1,
                        tier=BackendTier.OFFLINE,
                        phase=RuntimePhase.FAILED,
                        subphase="start_failed",
                        owner_lease=None,
                        startup_owner_id=None,
                        failures=(FailureSnapshot("START_FAILED", detail, "start"),),
                    )
                )
        self._emit_progress(RuntimeProgressPhase.FAILED)
        return ServiceLifecycleResult(status="failed", error=LaunchFailedError(detail))

    def _record_core_failure(self, owner_id: str, detail: str) -> None:
        with self._command_lock():
            current = self._runtime_record.read()
            if current.owner_lease is not None and current.owner_lease.owner_id == owner_id:
                components = tuple(
                    replace(
                        item,
                        state=ComponentState.FAILED,
                        detail=detail,
                        pid=None,
                    )
                    if item.component is RuntimeComponent.GODOT_AUTHORITY
                    else item
                    for item in current.components
                )
                self._runtime_record.write(
                    replace(
                        current,
                        revision=current.revision + 1,
                        tier=BackendTier.CORE_READY,
                        phase=RuntimePhase.FAILED,
                        subphase="world_failed",
                        components=components,
                        failures=(FailureSnapshot("WORLD_FAILED", detail, "world"),),
                    )
                )
        self._stop_authority_only()

    def _with_authority_evidence(self, observation: RuntimeObservation) -> RuntimeObservation:
        authority = self._authority_process
        if authority is None:
            return observation
        components = tuple(
            ComponentSnapshot(
                component=item.component,
                state=item.state,
                detail=item.detail,
                pid=authority.pid,
                executable=item.executable,
                birth_identity=item.birth_identity,
            )
            if item.component is RuntimeComponent.GODOT_AUTHORITY
            else item
            for item in observation.components
        )
        if not any(
            item.component is RuntimeComponent.GODOT_AUTHORITY for item in components
        ):
            components += (
                ComponentSnapshot(
                    RuntimeComponent.GODOT_AUTHORITY,
                    ComponentState.READY,
                    pid=authority.pid,
                ),
            )
        return replace(observation, components=components)

    def _stop_authority_only(self) -> Optional[str]:
        authority = self._authority_process
        if authority is not None and self._authority_host is not None:
            try:
                self._authority_host.stop(authority)
            except Exception as error:  # noqa: BLE001 - retain Core availability
                self._authority_process = None
                return str(error)
        self._authority_process = None
        return None

    def _stop_owned_resources(self) -> Optional[str]:
        errors = []
        authority_error = self._stop_authority_only()
        if authority_error:
            errors.append(f"Godot authority shutdown failed: {authority_error}")
        try:
            core_result = self._stop_core()
            if core_result.status not in {"stopped", "already_stopped"}:
                errors.append(str(core_result.error or "Core shutdown was not confirmed"))
        except Exception as error:  # noqa: BLE001 - preserve typed start failure
            errors.append(f"Core shutdown failed: {error}")
        return "; ".join(errors) if errors else None

    def _record_stop_failure(self, detail: str) -> None:
        with self._command_lock():
            current = self._runtime_record.read()
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    phase=RuntimePhase.FAILED,
                    subphase="stop_failed",
                    failures=(FailureSnapshot("STOP_INCOMPLETE", detail, "stop"),),
                )
            )

    def _owner_matches(self, owner_id: str) -> bool:
        record = self._runtime_record.read()
        return record.owner_lease is not None and record.owner_lease.owner_id == owner_id

    def _startup_claim_matches(self, owner_id: str) -> bool:
        record = self._runtime_record.read()
        return record.startup_owner_id == owner_id and record.phase is RuntimePhase.CORE_STARTING

    @staticmethod
    def _offline_snapshot(record: RuntimeSnapshotV1, *, phase: RuntimePhase, detail: str) -> RuntimeSnapshotV1:
        return replace(
            record,
            revision=record.revision + 1,
            tier=BackendTier.OFFLINE,
            phase=phase,
            owner_lease=None,
            startup_owner_id=None,
            failures=(FailureSnapshot("STALE_GENERATION", detail, "preflight"),),
        )

    @staticmethod
    def _recovery_detail(snapshot: RuntimeSnapshotV1) -> str:
        return snapshot.failures[0].detail if snapshot.failures else "Runtime snapshot recovery is required"

    def _emit_progress(self, phase: RuntimeProgressPhase) -> None:
        if self._progress_callback is not None:
            self._progress_callback(phase)

    def _elapsed_since(self, started_at: Optional[float]) -> Optional[float]:
        if started_at is None:
            return None
        return max(0.0, self._monotonic() - started_at)


def _append_timing(
    timings: tuple[TimingSnapshot, ...], phase: str, elapsed_seconds: Optional[float]
) -> tuple[TimingSnapshot, ...]:
    if elapsed_seconds is None:
        return timings
    completed = TimingSnapshot(
        phase=phase,
        duration_ms=max(0, int(elapsed_seconds * 1000)),
    )
    return tuple(item for item in timings if item.phase != phase) + (completed,)
