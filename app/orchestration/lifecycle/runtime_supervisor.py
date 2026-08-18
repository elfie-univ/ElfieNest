"""Core/World lifecycle coordinator backed by RuntimeSnapshotV1."""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from typing import Callable, Iterator, MutableMapping, Optional

from app.orchestration.lifecycle.ports import (
    AuthorityHostPort,
    AuthorityProcess,
    LifecycleLease,
    ProcessSnapshot,
    RecordedAuthorityProcess,
    RuntimeRecordPort,
)
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
    RuntimeProjectionV1,
    RuntimeSnapshotV1,
    RuntimeTarget,
    TimingSnapshot,
)
from app.orchestration.lifecycle.types import (
    AuthorityHostError,
    LaunchFailedError,
    LifecycleBusyError,
    LifecycleCancelledError,
    RuntimeIdentityUnavailableError,
    ServiceLifecycleError,
    ServiceLifecycleResult,
    SnapshotRecoveryRequiredError,
)

ObservationProbe = Callable[[], RuntimeObservation]
StartCore = Callable[[Callable[[], bool]], ServiceLifecycleResult]
StopCore = Callable[[], ServiceLifecycleResult]
OwnedRecord = Callable[[], bool]
CoreProcessPresence = Callable[[int], bool]
ProgressCallback = Callable[[RuntimeProgressPhase], None]
CommandLeaseFactory = Callable[[], LifecycleLease]
ModelProjectionProbe = Callable[[], ModelHealthProjection]
CancellationProbe = Callable[[], bool]
DataHomePreparation = Callable[[], None]


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
        authority_recovery_host: Optional[AuthorityHostPort] = None,
        authority_timeout_seconds: float = 10.0,
        model_timeout_seconds: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        progress_callback: Optional[ProgressCallback] = None,
        command_lease_factory: Optional[CommandLeaseFactory] = None,
        model_projection_probe: Optional[ModelProjectionProbe] = None,
        child_environment: Optional[MutableMapping[str, str]] = None,
        prepare_data_home: Optional[DataHomePreparation] = None,
        core_process_identity: Optional[Callable[[int], ProcessSnapshot]] = None,
        core_process_exists: Optional[CoreProcessPresence] = None,
    ) -> None:
        self._runtime_record = runtime_record
        self._prepare_data_home = prepare_data_home
        self._health_probe = health_probe
        self._start_core = start_core
        self._stop_core = stop_core
        self._owns_pid_record = owns_pid_record
        self._authority_host = authority_host
        # Core-resident World convergence normally owns the live Godot handle.
        # A separate recovery host lets the parent clean an exact recorded
        # authority after Core has crashed, without ever starting a second one.
        self._authority_recovery_host = authority_recovery_host
        self._authority_timeout_seconds = authority_timeout_seconds
        self._model_timeout_seconds = model_timeout_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._progress_callback = progress_callback
        self._command_lease_factory = command_lease_factory
        self._model_projection_probe = model_projection_probe
        self._child_environment = child_environment
        self._core_process_identity = core_process_identity
        self._core_process_exists = core_process_exists
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
        cancel_check: Optional[CancellationProbe] = None,
    ) -> ServiceLifecycleResult:
        """Reserve one generation, reach Core, then converge World safely."""
        operation_id = correlation_id or uuid.uuid4().hex
        try:
            record_before_start = self._initialize_and_read()
        except SnapshotRecoveryRequiredError as error:
            return self._operation_result(
                ServiceLifecycleResult(
                    status="failed", error=LaunchFailedError(str(error))
                ),
                operation_id,
            )

        existing_attachment: Optional[tuple[str, Optional[int]]] = None
        writer_recovery_required = False
        with self._command_lock():
            record_before_start = self._runtime_record.read()
            if record_before_start.phase is RuntimePhase.RECOVERY_REQUIRED:
                return self._operation_result(
                    ServiceLifecycleResult(
                        status="failed",
                        error=LaunchFailedError(
                            self._recovery_detail(record_before_start)
                        ),
                    ),
                    operation_id,
                )
            if record_before_start.startup_owner_id is not None:
                if record_before_start.startup_owner_id == owner_id:
                    return self._operation_result(
                        ServiceLifecycleResult(
                            status="failed",
                            error=LifecycleBusyError(
                                "Runtime startup is already owned by this command"
                            ),
                        ),
                        operation_id,
                    )
                return self._operation_result(
                    ServiceLifecycleResult(
                        status="failed",
                        error=LifecycleBusyError(
                            "Runtime startup is already owned by another command"
                        ),
                    ),
                    operation_id,
                )
            if record_before_start.phase in {
                RuntimePhase.QUIESCING,
                RuntimePhase.WORLD_STOPPING,
                RuntimePhase.MODEL_LEASE_RELEASING,
                RuntimePhase.CORE_STOPPING,
            }:
                return self._operation_result(
                    ServiceLifecycleResult(
                        status="failed",
                        error=LifecycleBusyError(
                            "Runtime is stopping; wait for OFFLINE before starting again"
                        ),
                    ),
                    operation_id,
                )
            if (
                record_before_start.owner_lease is not None
                and record_before_start.tier is not BackendTier.OFFLINE
            ):
                incomplete_stop = next(
                    (
                        failure
                        for failure in record_before_start.failures
                        if failure.code in {"STOP_INCOMPLETE", "WORLD_STOP_INCOMPLETE"}
                    ),
                    None,
                )
                if incomplete_stop is not None:
                    return self._operation_result(
                        ServiceLifecycleResult(
                            status="failed",
                            error=LaunchFailedError(
                                "Previous Runtime shutdown is incomplete; "
                                f"retry stop before starting a new generation: {incomplete_stop.detail}"
                            ),
                        ),
                        operation_id,
                    )
                if self._owns_pid_record():
                    existing_attachment = (
                        record_before_start.owner_lease.owner_id,
                        record_before_start.component(RuntimeComponent.CORE).pid,
                    )
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
                else:
                    if not self._recorded_core_is_absent(record_before_start):
                        return self._operation_result(
                            ServiceLifecycleResult(
                                status="failed",
                                error=LaunchFailedError(
                                    "Recorded Core process is still present or cannot be verified; "
                                    "refusing to replace its Runtime generation"
                                ),
                            ),
                            operation_id,
                        )
                    record_before_start = self._offline_snapshot(
                        record_before_start,
                        phase=RuntimePhase.PREFLIGHT,
                        detail="stale generation reconciled before restart",
                    )
                    writer_recovery_required = True

            if (
                record_before_start.writer_credential_digest is not None
                and record_before_start.owner_lease is None
                and record_before_start.startup_owner_id is None
            ):
                if not self._recorded_core_is_absent(record_before_start):
                    return self._operation_result(
                        ServiceLifecycleResult(
                            status="failed",
                            error=LaunchFailedError(
                                "Runtime has a stale writer credential while its recorded Core "
                                "process is still present or cannot be verified"
                            ),
                        ),
                        operation_id,
                    )
                writer_recovery_required = True

            # An attached caller waits after releasing this command lease so
            # the existing Core can publish World readiness in parallel.
            if existing_attachment is None:
                generation = record_before_start.generation + 1
                writer_handoff = self._begin_writer_handoff(
                    generation=generation,
                    owner_id=owner_id,
                    recover_stale=writer_recovery_required,
                )
                if writer_handoff is not None and self._child_environment is not None:
                    self._child_environment["ELFIENEST_RUNTIME_WRITER_TOKEN"] = (
                        writer_handoff.token
                    )
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
                    correlation_id=operation_id,
                    owner_lease=None,
                    startup_owner_id=owner_id,
                    writer_credential_digest=(
                        None if writer_handoff is None else writer_handoff.digest
                    ),
                )
                self._runtime_record.write(starting)

        if existing_attachment is not None:
            existing_owner_id, attached_pid = existing_attachment
            wait_error = self._wait_for_existing_target(
                existing_owner_id,
                wait_target,
                cancel_check,
            )
            return self._operation_result(
                ServiceLifecycleResult(
                    status="failed" if wait_error is not None else "already_running",
                    pid=attached_pid,
                    error=wait_error,
                ),
                operation_id,
            )

        self._emit_progress(RuntimeProgressPhase.STARTING)
        self._start_started_at = self._monotonic()
        self._world_started_at = None

        if self._startup_cancelled(owner_id, cancel_check):
            return self._cancel_start(
                owner_id, "Runtime startup was cancelled", operation_id
            )

        def core_and_gateway_ready() -> bool:
            if self._startup_cancelled(owner_id, cancel_check):
                raise LifecycleCancelledError("Runtime startup was cancelled")
            return self._health_probe().core_ready

        try:
            result = self._start_core(core_and_gateway_ready)
        except LifecycleCancelledError as error:
            return self._cancel_start(owner_id, str(error), operation_id)
        except Exception as error:  # noqa: BLE001 - convert adapter failures to typed state
            return self._fail_start(
                owner_id, f"Core startup failed: {error}", operation_id
            )
        if result.status not in {"started", "already_running"}:
            return self._fail_start(
                owner_id, str(result.error or "Core startup failed"), operation_id
            )

        if self._startup_cancelled(owner_id, cancel_check):
            return self._cancel_start(
                owner_id, "Runtime startup was cancelled", operation_id
            )

        try:
            observation = self._health_probe()
        except Exception as error:  # noqa: BLE001 - startup must release its claim
            return self._fail_start(
                owner_id, f"Core readiness probe failed: {error}", operation_id
            )
        if not observation.core_ready:
            return self._fail_start(
                owner_id, "Core did not publish CORE_READY", operation_id
            )
        try:
            promoted = self._promote_core_ready(owner_id, observation, pid=result.pid)
        except RuntimeIdentityUnavailableError as error:
            return self._fail_start(owner_id, str(error), operation_id)
        if not promoted:
            return self._cancel_start(
                owner_id,
                "Runtime startup was cancelled before CORE_READY",
                operation_id,
            )
        self._emit_progress(RuntimeProgressPhase.CORE_READY)

        if cancel_check is not None and cancel_check():
            return self._cancel_start(
                owner_id, "Runtime startup was cancelled", operation_id
            )

        if (
            desired_target.rank >= RuntimeTarget.WORLD.rank
            and wait_target.rank >= RuntimeTarget.WORLD.rank
        ):
            if self._authority_host is not None:
                try:
                    self._start_authority(owner_id)
                except AuthorityHostError as error:
                    if self._owner_operation_cancelled(owner_id, cancel_check):
                        return self._cancel_start(owner_id, str(error), operation_id)
                    self._record_core_failure(owner_id, str(error))
                    self._emit_progress(RuntimeProgressPhase.FAILED)
                    return self._operation_result(
                        ServiceLifecycleResult(
                            status="failed",
                            pid=result.pid,
                            command=result.command,
                            error=LaunchFailedError(str(error)),
                        ),
                        operation_id,
                    )
                if not self._wait_for_world(owner_id):
                    if self._owner_operation_cancelled(owner_id, cancel_check):
                        return self._cancel_start(
                            owner_id,
                            "Runtime startup was cancelled before World readiness",
                            operation_id,
                        )
                    detail = self._authority_readiness_failure_detail()
                    self._record_core_failure(owner_id, detail)
                    self._emit_progress(RuntimeProgressPhase.FAILED)
                    return self._operation_result(
                        ServiceLifecycleResult(
                            status="failed",
                            pid=result.pid,
                            command=result.command,
                            error=LaunchFailedError(detail),
                        ),
                        operation_id,
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
                if self._owner_operation_cancelled(owner_id, cancel_check):
                    return self._cancel_start(
                        owner_id,
                        "Runtime startup was cancelled before World readiness",
                        operation_id,
                    )
                return self._operation_result(
                    ServiceLifecycleResult(
                        status="failed",
                        pid=result.pid,
                        command=result.command,
                        error=LaunchFailedError(
                            "Runtime startup was cancelled before World readiness completed"
                        ),
                    ),
                    operation_id,
                )
        if world_reached:
            self._emit_progress(RuntimeProgressPhase.WORLD_READY)
        if (
            desired_target is RuntimeTarget.NORMAL
            and wait_target is RuntimeTarget.NORMAL
        ):
            if not self._wait_for_normal(owner_id, cancel_check):
                if self._owner_operation_cancelled(owner_id, cancel_check):
                    return self._cancel_start(
                        owner_id,
                        "Runtime startup was cancelled before Normal readiness",
                        operation_id,
                    )
                detail = self._model_readiness_failure_detail()
                return self._operation_result(
                    ServiceLifecycleResult(
                        status="failed",
                        pid=result.pid,
                        command=result.command,
                        error=LaunchFailedError(detail),
                    ),
                    operation_id,
                )
        return self._operation_result(result, operation_id)

    def stop(self, *, correlation_id: Optional[str] = None) -> ServiceLifecycleResult:
        """Quiesce, release the owned authority and retain an OFFLINE snapshot."""
        operation_id = correlation_id or uuid.uuid4().hex
        interrupted_stop: Optional[RuntimeSnapshotV1] = None
        with self._command_lock():
            record = self._runtime_record.read()
            if record.phase is RuntimePhase.RECOVERY_REQUIRED:
                if not self._core_identity_present():
                    return self._operation_result(
                        ServiceLifecycleResult(
                            status="already_stopped",
                            error=None,
                        ),
                        operation_id,
                    )
                return self._operation_result(
                    ServiceLifecycleResult(
                        status="failed",
                        error=LaunchFailedError(self._recovery_detail(record)),
                    ),
                    operation_id,
                )
            if (
                record.phase is RuntimePhase.OFFLINE
                and record.tier is BackendTier.OFFLINE
                and record.owner_lease is None
                and record.startup_owner_id is None
            ):
                return self._operation_result(
                    ServiceLifecycleResult(status="already_stopped"),
                    operation_id,
                )
            if record.phase in {
                RuntimePhase.QUIESCING,
                RuntimePhase.WORLD_STOPPING,
                RuntimePhase.MODEL_LEASE_RELEASING,
                RuntimePhase.CORE_STOPPING,
            }:
                if self._core_identity_present():
                    return self._operation_result(
                        ServiceLifecycleResult(
                            status="failed",
                            error=LifecycleBusyError(
                                "Runtime shutdown is already in progress; wait for OFFLINE"
                            ),
                        ),
                        operation_id,
                    )
                interrupted_stop = record
            if interrupted_stop is None and (
                record.owner_lease is not None or record.startup_owner_id is not None
            ):
                self._runtime_record.write(
                    replace(
                        record,
                        revision=record.revision + 1,
                        phase=RuntimePhase.QUIESCING,
                        subphase="stop_requested",
                    )
                )
        if interrupted_stop is not None:
            return self._recover_interrupted_stop(interrupted_stop, operation_id)
        self._emit_progress(RuntimeProgressPhase.STOPPING)
        stop_started_at = self._monotonic()
        self._transition_stop_phase(RuntimePhase.WORLD_STOPPING, "world")
        authority = self._authority_process or self._recorded_authority_process()
        authority_host = (
            self._authority_host
            if self._authority_process is not None
            else self._authority_recovery_host
        )
        authority_error: Optional[Exception] = None
        authority_stopped = False
        if authority is not None:
            if authority_host is None:
                authority_error = RuntimeError(
                    "Recorded Godot authority cannot be stopped without an authority host"
                )
            else:
                try:
                    authority_host.stop(authority)
                    authority_stopped = True
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
        if authority_stopped and authority is not None:
            self._clear_recorded_authority(authority.pid)
        world_cleanup_error = self._world_cleanup_failure()
        if (
            result.status in {"stopped", "already_stopped"}
            and authority_error is None
            and world_cleanup_error is None
        ):
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
                        writer_credential_digest=None,
                        failures=(),
                        timings=_append_timing(
                            current.timings,
                            "stop",
                            self._monotonic() - stop_started_at,
                        ),
                    )
                )
                revoke = getattr(self._runtime_record, "revoke_writer_handoff", None)
                if callable(revoke):
                    revoke()
            return self._operation_result(result, operation_id)

        detail_parts = []
        if authority_error is not None:
            detail_parts.append(f"Godot authority shutdown failed: {authority_error}")
        if world_cleanup_error is not None:
            detail_parts.append(f"World cleanup incomplete: {world_cleanup_error}")
        if result.status == "failed":
            detail_parts.append(str(result.error or "Core shutdown failed"))
        else:
            detail_parts.append("Core did not confirm shutdown")
        detail = "; ".join(detail_parts)
        self._record_stop_failure(detail)
        return self._operation_result(
            ServiceLifecycleResult(
                status="failed",
                pid=result.pid,
                command=result.command,
                error=LaunchFailedError(detail),
            ),
            operation_id,
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
        if projection.tier is not BackendTier.OFFLINE:
            try:
                core_is_present = self._owns_pid_record()
            except (OSError, RuntimeError, ValueError):
                core_is_present = True
            if not core_is_present:
                projection = replace(
                    projection,
                    tier=BackendTier.OFFLINE,
                    phase=RuntimePhase.FAILED,
                    subphase="core_missing",
                    reached_target=None,
                    components=(),
                    endpoints=(),
                    owner_lease=None,
                    startup_owner_id=None,
                    failures=(
                        FailureSnapshot(
                            "CORE_NOT_RUNNING",
                            "Core process is no longer present for this Runtime generation",
                            "status",
                        ),
                    ),
                )
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
            prepared = self._prepare_data_home is not None
            if self._prepare_data_home is not None:
                self._prepare_data_home()
            initializer = getattr(self._runtime_record, "initialize_if_fresh", None)
            if callable(initializer):
                if prepared:
                    return initializer(allow_existing_root=True)
                return initializer()
            return self._runtime_record.read()

    def _begin_writer_handoff(
        self, *, generation: int, owner_id: str, recover_stale: bool = False
    ):
        begin = getattr(self._runtime_record, "begin_writer_handoff", None)
        if not callable(begin):
            return None
        return begin(
            generation=generation,
            owner_id=owner_id,
            recover_stale=recover_stale,
        )

    def _recorded_core_is_absent(self, record: RuntimeSnapshotV1) -> bool:
        """Return true only when replacing the recorded Core is safe."""
        pid = record.component(RuntimeComponent.CORE).pid
        if pid is None:
            return True
        if self._core_process_exists is not None:
            try:
                return not self._core_process_exists(pid)
            except (OSError, RuntimeError, ValueError):
                return False
        try:
            return not self._owns_pid_record()
        except (OSError, RuntimeError, ValueError):
            return False

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
        if pid is None:
            raise RuntimeIdentityUnavailableError(
                "Core startup returned no PID"
            )
        if self._core_process_identity is None:
            raise RuntimeIdentityUnavailableError(
                "the process inspector did not provide a birth-identity reader"
            )
        try:
            identity = self._core_process_identity(pid)
        except (OSError, RuntimeError, ValueError) as error:
            raise RuntimeIdentityUnavailableError(
                f"unable to inspect Core PID {pid}: {error}"
            ) from error
        if (
            identity.pid != pid
            or not identity.birth_identity
            or not identity.command
            or identity.cwd is None
        ):
            raise RuntimeIdentityUnavailableError(
                f"Core PID {pid} returned incomplete process identity"
            )
        with self._command_lock():
            current = self._runtime_record.read()
            if current.startup_owner_id != owner_id:
                return False
            if current.phase is not RuntimePhase.CORE_STARTING:
                return False
            components = tuple(
                replace(item, pid=pid)
                if item.component in {RuntimeComponent.CORE, RuntimeComponent.GATEWAY}
                else item
                for item in observation.components
            )
            components = tuple(
                replace(
                    item,
                    executable=identity.command[0],
                    birth_identity=identity.birth_identity,
                    cwd=str(identity.cwd.resolve()),
                )
                if item.component
                in {RuntimeComponent.CORE, RuntimeComponent.GATEWAY}
                else item
                for item in components
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
        if not self._startup_claim_matches(owner_id) and not self._owner_matches(
            owner_id
        ):
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

    def _wait_for_world_handoff(
        self,
        owner_id: str,
        *,
        cancel_check: Optional[CancellationProbe] = None,
    ) -> Optional[bool]:
        """Wait for the Core-resident worker to publish WORLD_READY."""
        deadline = self._monotonic() + self._authority_timeout_seconds
        while True:
            if cancel_check is not None and cancel_check():
                return False
            current = self._runtime_record.read()
            if current.owner_lease is None or current.owner_lease.owner_id != owner_id:
                return None
            if current.tier is BackendTier.WORLD_READY:
                return True
            if current.phase in {
                RuntimePhase.FAILED,
                RuntimePhase.RECOVERY_REQUIRED,
                RuntimePhase.OFFLINE,
                RuntimePhase.QUIESCING,
                RuntimePhase.WORLD_STOPPING,
                RuntimePhase.MODEL_LEASE_RELEASING,
                RuntimePhase.CORE_STOPPING,
            }:
                return False
            if self._monotonic() >= deadline:
                return False
            self._sleeper(0.1)

    def _wait_for_existing_target(
        self,
        owner_id: str,
        wait_target: RuntimeTarget,
        cancel_check: Optional[CancellationProbe],
    ) -> Optional[ServiceLifecycleError]:
        """Wait for an already-owned generation without taking its ownership."""
        if wait_target.rank < RuntimeTarget.WORLD.rank:
            return None
        world = self._wait_for_world_handoff(owner_id, cancel_check=cancel_check)
        if world is not True:
            if cancel_check is not None and cancel_check():
                return LifecycleCancelledError(
                    "Runtime wait was cancelled before World readiness"
                )
            return LaunchFailedError(
                "Runtime generation did not reach WORLD_READY before the wait timeout"
            )
        if wait_target is not RuntimeTarget.NORMAL:
            return None
        if self._wait_for_normal(owner_id, cancel_check):
            return None
        if cancel_check is not None and cancel_check():
            return LifecycleCancelledError(
                "Runtime wait was cancelled before Normal readiness"
            )
        return LaunchFailedError(self._model_readiness_failure_detail())

    def _wait_for_normal(
        self,
        owner_id: str,
        cancel_check: Optional[CancellationProbe],
    ) -> bool:
        """Wait for the derived Normal target without probing the model."""
        if self._model_projection_probe is None:
            return False
        deadline = self._monotonic() + self._model_timeout_seconds
        while True:
            if self._owner_operation_cancelled(owner_id, cancel_check):
                return False
            current = self._runtime_record.read()
            if current.tier is not BackendTier.WORLD_READY:
                return False
            try:
                model = self._model_projection_probe()
            except (OSError, RuntimeError, ValueError):
                model = None
            if model is not None and model.state is ModelOverallState.READY:
                return True
            if self._monotonic() >= deadline:
                return False
            self._sleeper(0.1)

    def _model_readiness_failure_detail(self) -> str:
        if self._model_projection_probe is None:
            return "Normal readiness requires a model health projection"
        try:
            model = self._model_projection_probe()
        except (OSError, RuntimeError, ValueError) as error:
            return f"Model health projection failed before Normal readiness: {error}"
        return (
            "Model service did not reach READY before Normal readiness timeout "
            f"(state={model.state.value})"
        )

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

    def _core_identity_present(self) -> bool:
        """Fail closed when deciding whether an interrupted stop may be retried."""
        try:
            return self._owns_pid_record()
        except (OSError, RuntimeError, ValueError):
            return True

    def _clear_recorded_authority(self, pid: int) -> None:
        """Remove a recorded authority only after its owner confirms stop."""
        with self._command_lock():
            current = self._runtime_record.read()
            component = current.component(RuntimeComponent.GODOT_AUTHORITY)
            if component.pid != pid:
                return
            components = tuple(
                replace(
                    item,
                    state=ComponentState.ABSENT,
                    detail="",
                    pid=None,
                )
                if item.component is RuntimeComponent.GODOT_AUTHORITY
                else item
                for item in current.components
            )
            self._runtime_record.write(
                replace(current, revision=current.revision + 1, components=components)
            )

    def _world_cleanup_failure(self) -> Optional[str]:
        """Return explicit World cleanup evidence instead of hiding it at OFFLINE."""
        try:
            current = self._runtime_record.read()
        except (OSError, RuntimeError, ValueError) as error:
            return f"unable to verify World cleanup: {error}"
        for failure in current.failures:
            if failure.code == "WORLD_STOP_INCOMPLETE":
                return failure.detail
        return None

    def _recover_interrupted_stop(
        self,
        record: RuntimeSnapshotV1,
        operation_id: str,
    ) -> ServiceLifecycleResult:
        """Reconcile a stopped Core before allowing a new generation.

        A crashed stop command may leave the durable phase in a stopping state.
        Only after the exact Core is absent do we recover the recorded Godot
        authority and ask the normal Core stop path to prove its endpoints are
        gone.  Unknown port occupants remain untouched and keep the operation
        failed rather than being mistaken for a clean OFFLINE result.
        """
        authority = self._recorded_authority_process()
        authority_error: Optional[Exception] = None
        if authority is not None:
            authority_host = self._authority_recovery_host or self._authority_host
            if authority_host is None:
                authority_error = RuntimeError(
                    "Recorded Godot authority cannot be recovered without an authority host"
                )
            else:
                try:
                    authority_host.stop(authority)
                except Exception as error:  # noqa: BLE001 - preserve residual evidence
                    authority_error = error
        try:
            core_result = self._stop_core()
        except Exception as error:  # noqa: BLE001 - convert adapter failure
            core_result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"Core shutdown failed: {error}"),
            )
        if authority_error is None and core_result.status in {
            "stopped",
            "already_stopped",
        }:
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
                        writer_credential_digest=None,
                        failures=(),
                    )
                )
                revoke = getattr(self._runtime_record, "revoke_writer_handoff", None)
                if callable(revoke):
                    revoke()
            return self._operation_result(
                ServiceLifecycleResult(
                    status="already_stopped",
                    pid=core_result.pid,
                    command=core_result.command,
                ),
                operation_id,
            )

        detail_parts = []
        if authority_error is not None:
            detail_parts.append(f"Godot authority recovery failed: {authority_error}")
        if core_result.status == "failed":
            detail_parts.append(str(core_result.error or "Core shutdown failed"))
        else:
            detail_parts.append("Core shutdown was not confirmed")
        detail = "; ".join(detail_parts)
        self._record_stop_failure(detail)
        return self._operation_result(
            ServiceLifecycleResult(
                status="failed",
                pid=core_result.pid,
                command=core_result.command,
                error=LaunchFailedError(detail),
            ),
            operation_id,
        )

    def _fail_start(
        self,
        owner_id: str,
        detail: str,
        operation_id: Optional[str] = None,
    ) -> ServiceLifecycleResult:
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
        return self._operation_result(
            ServiceLifecycleResult(status="failed", error=LaunchFailedError(detail)),
            operation_id,
        )

    def _cancel_start(
        self,
        owner_id: str,
        detail: str,
        operation_id: Optional[str] = None,
    ) -> ServiceLifecycleResult:
        """Release resources acquired by a cancelled start without overwriting stop."""
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
                        subphase="start_cancelled",
                        owner_lease=None,
                        startup_owner_id=None,
                        failures=(FailureSnapshot("START_CANCELLED", detail, "start"),),
                    )
                )
        self._emit_progress(RuntimeProgressPhase.FAILED)
        return self._operation_result(
            ServiceLifecycleResult(
                status="failed",
                error=LifecycleCancelledError(detail),
            ),
            operation_id,
        )

    def _operation_result(
        self,
        result: ServiceLifecycleResult,
        operation_id: Optional[str],
    ) -> ServiceLifecycleResult:
        if operation_id is None:
            return result
        try:
            generation = self._runtime_record.read().generation
        except (OSError, RuntimeError, ValueError):
            generation = None
        return replace(result, operation_id=operation_id, generation=generation)

    def _record_core_failure(self, owner_id: str, detail: str) -> None:
        with self._command_lock():
            current = self._runtime_record.read()
            if (
                current.owner_lease is not None
                and current.owner_lease.owner_id == owner_id
            ):
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

    def _with_authority_evidence(
        self, observation: RuntimeObservation
    ) -> RuntimeObservation:
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
        live_authority = self._authority_process
        authority_error = self._stop_authority_only()
        if authority_error:
            recovery_host = self._authority_recovery_host
            if live_authority is not None and recovery_host is not None:
                try:
                    recovery_host.stop(RecordedAuthorityProcess(live_authority.pid))
                    authority_error = None
                except Exception as error:  # noqa: BLE001 - retain residual evidence
                    authority_error = f"{authority_error}; recovery failed: {error}"
            if authority_error:
                errors.append(f"Godot authority shutdown failed: {authority_error}")
        elif live_authority is None:
            recorded = self._recorded_authority_process()
            recovery_host = self._authority_recovery_host
            if recorded is not None and recovery_host is not None:
                try:
                    recovery_host.stop(recorded)
                except Exception as error:  # noqa: BLE001 - preserve typed start failure
                    errors.append(f"Godot authority recovery failed: {error}")
            elif recorded is not None:
                errors.append(
                    "Recorded Godot authority cannot be recovered without an authority host"
                )
        try:
            core_result = self._stop_core()
            if core_result.status not in {"stopped", "already_stopped"}:
                errors.append(
                    str(core_result.error or "Core shutdown was not confirmed")
                )
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
        return (
            record.owner_lease is not None
            and record.owner_lease.owner_id == owner_id
            and record.phase
            not in {
                RuntimePhase.QUIESCING,
                RuntimePhase.WORLD_STOPPING,
                RuntimePhase.MODEL_LEASE_RELEASING,
                RuntimePhase.CORE_STOPPING,
            }
        )

    def _startup_cancelled(
        self,
        owner_id: str,
        cancel_check: Optional[CancellationProbe],
    ) -> bool:
        if cancel_check is not None and cancel_check():
            return True
        record = self._runtime_record.read()
        return (
            record.startup_owner_id != owner_id
            or record.phase is not RuntimePhase.CORE_STARTING
        )

    def _owner_operation_cancelled(
        self,
        owner_id: str,
        cancel_check: Optional[CancellationProbe],
    ) -> bool:
        if cancel_check is not None and cancel_check():
            return True
        return not self._owner_matches(owner_id)

    def _startup_claim_matches(self, owner_id: str) -> bool:
        record = self._runtime_record.read()
        return (
            record.startup_owner_id == owner_id
            and record.phase is RuntimePhase.CORE_STARTING
        )

    @staticmethod
    def _offline_snapshot(
        record: RuntimeSnapshotV1, *, phase: RuntimePhase, detail: str
    ) -> RuntimeSnapshotV1:
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
        return (
            snapshot.failures[0].detail
            if snapshot.failures
            else "Runtime snapshot recovery is required"
        )

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
