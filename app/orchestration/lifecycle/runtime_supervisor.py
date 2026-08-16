"""Component-aware Runtime lifecycle workflow."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Optional

from app.orchestration.lifecycle.ports import (
    AuthorityHostPort,
    AuthorityProcess,
    RecordedAuthorityProcess,
    RuntimeRecordPort,
)
from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    OwnerLease,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
    RuntimeProgressPhase,
)
from app.orchestration.lifecycle.types import (
    AuthorityHostError,
    LaunchFailedError,
    ServiceLifecycleResult,
)

HealthProbe = Callable[[], RuntimeHealth]
StartCore = Callable[[Callable[[], bool]], ServiceLifecycleResult]
StopCore = Callable[[], ServiceLifecycleResult]
PrepareOptionalComponent = Callable[[], None]
OwnedRecord = Callable[[], bool]
ProgressCallback = Callable[[RuntimeProgressPhase], None]


class RuntimeSupervisor:
    """Coordinate Core and Godot authority while persisting one Runtime generation."""

    def __init__(
        self,
        *,
        runtime_record: RuntimeRecordPort,
        health_probe: HealthProbe,
        start_core: StartCore,
        stop_core: StopCore,
        prepare_optional_component: PrepareOptionalComponent = lambda: None,
        owns_pid_record: OwnedRecord = lambda: True,
        authority_host: Optional[AuthorityHostPort] = None,
        authority_timeout_seconds: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self._runtime_record = runtime_record
        self._health_probe = health_probe
        self._start_core = start_core
        self._stop_core = stop_core
        self._prepare_optional_component = prepare_optional_component
        self._owns_pid_record = owns_pid_record
        self._authority_host = authority_host
        self._authority_timeout_seconds = authority_timeout_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._progress_callback = progress_callback
        self._authority_process: Optional[AuthorityProcess] = None

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        """Start Core once and persist its full component-generation receipt."""
        record_before_start = self._runtime_record.read()
        if record_before_start.startup_owner_id is not None:
            return ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError("Runtime startup is already owned"),
            )
        health_before_start = self._health_probe()
        self._prepare_optional_component()
        authority_already_owned = (
            record_before_start.owner_lease is not None
            and self._runtime_state(health_before_start)
            in {RuntimeHealthState.READY, RuntimeHealthState.DEGRADED}
        )
        if record_before_start.owner_lease is not None and not authority_already_owned:
            # A crashed Core can leave the generation receipt behind. Only keep
            # the hard restart guard when the recorded service is still live;
            # otherwise the stale lease must not block the next launch forever.
            if self._owns_pid_record():
                return ServiceLifecycleResult(
                    status="failed",
                    error=LaunchFailedError(
                        "Existing Runtime generation authority is not ready; run restart"
                    ),
                )
            self._runtime_record.remove()
            record_before_start = self._runtime_record.read()
        if not authority_already_owned:
            self._write_starting_record(owner_id, record_before_start)
        self._emit_progress(RuntimeProgressPhase.STARTING)
        core_ready_emitted = False

        def core_and_gateway_ready() -> bool:
            nonlocal core_ready_emitted
            # start_service invokes its health checker after the Core process has
            # been launched and registered. Starting the hidden authority from
            # that first probe lets its Web load/reconnect overlap Core startup,
            # while the ownership guard keeps external checkouts untouched.
            if (
                self._authority_host is not None
                and self._authority_process is None
                and not authority_already_owned
                and self._owns_pid_record()
            ):
                self._start_authority(owner_id)
            health = self._health_probe()
            core_ready = self._core_and_gateway_ready(health)
            if (
                core_ready
                and not core_ready_emitted
                and self._startup_claim_matches(owner_id)
            ):
                self._write_starting_record(owner_id, health)
                self._emit_progress(RuntimeProgressPhase.CORE_READY)
                core_ready_emitted = True
            return core_ready

        try:
            result = self._start_core(core_and_gateway_ready)
        except AuthorityHostError as error:
            return self._cleanup_after_authority_failure(
                ServiceLifecycleResult(status="failed"), str(error), owner_id=owner_id
            )
        if result.status not in {"started", "already_running"}:
            failed_health = self._health_probe()
            if self._startup_claim_matches(owner_id):
                self._runtime_record.write(
                    RuntimeHealth(
                        state=self._runtime_state(failed_health),
                        generation=self._runtime_record.read().generation,
                        owner_lease=None,
                        components=failed_health.components,
                        startup_owner_id=None,
                    )
                )
            self._emit_progress(RuntimeProgressPhase.FAILED)
            return result
        if not self._owns_pid_record():
            self._clear_starting_record(owner_id)
            return result
        if result.status == "already_running" and record_before_start.owner_lease:
            if self._runtime_state(health_before_start) in {
                RuntimeHealthState.READY,
                RuntimeHealthState.DEGRADED,
            }:
                return result
            return ServiceLifecycleResult(
                status="failed",
                pid=result.pid,
                command=result.command,
                error=LaunchFailedError(
                    "Existing Runtime generation authority is not ready; run restart"
                ),
            )
        if self._authority_host is not None:
            try:
                # Test doubles and already-running service paths may not call
                # the Core health checker. Keep a safe sequential fallback for
                # those paths; normal launches have already overlapped it above.
                if self._authority_process is None:
                    self._start_authority(owner_id)
            except AuthorityHostError as error:
                return self._cleanup_after_authority_failure(
                    result, str(error), owner_id=owner_id
                )
            if not self._wait_for_full_health(owner_id):
                return self._cleanup_after_authority_failure(
                    result,
                    self._authority_readiness_failure_detail(),
                    owner_id=owner_id,
                )
        if not authority_already_owned and not self._startup_claim_matches(owner_id):
            return self._cleanup_after_authority_failure(
                result,
                "Runtime startup was cancelled before readiness completed",
                owner_id=owner_id,
            )
        health = self._with_authority_process(self._health_probe())
        state = self._runtime_state(health)
        record = self._runtime_record.read()
        generation = (
            record.generation + 1
            if result.status == "started" or record.generation == 0
            else record.generation
        )
        if result.status == "started" and health_before_start.generation > generation:
            generation = health_before_start.generation + 1
        complete = RuntimeHealth(
            state=state,
            generation=generation,
            owner_lease=OwnerLease(owner_id=owner_id, generation=generation),
            components=health.components,
            startup_owner_id=None,
        )
        self._runtime_record.write(complete)
        self._emit_progress(RuntimeProgressPhase.READY)
        return result

    def _start_authority(self, owner_id: Optional[str] = None) -> None:
        """Launch exactly one authority process for the current generation."""
        if self._authority_host is None or self._authority_process is not None:
            return
        if owner_id is not None and not self._startup_claim_matches(owner_id):
            raise AuthorityHostError("Runtime startup was cancelled")
        self._emit_progress(RuntimeProgressPhase.AUTHORITY_STARTING)
        authority = self._authority_host.start()
        if authority is None:
            raise AuthorityHostError("Godot authority Runtime failed to start")
        if owner_id is not None and not self._startup_claim_matches(owner_id):
            # A public stop can win the race between the claim check and the
            # authority launch. Reap the just-created process before letting
            # the cancelled start unwind, even though the stop command did not
            # yet have its PID in the durable receipt.
            self._authority_host.stop(authority)
            raise AuthorityHostError("Runtime startup was cancelled")
        self._authority_process = authority
        self._write_starting_record_from_probe()

    def stop(self) -> ServiceLifecycleResult:
        """Stop the owned authority and Core; public Ollama is never signalled."""
        record = self._runtime_record.read()
        if record.owner_lease is not None or record.startup_owner_id is not None:
            self._runtime_record.write(
                replace(record, state=RuntimeHealthState.STOPPING)
            )
        self._emit_progress(RuntimeProgressPhase.STOPPING)
        authority = self._authority_process or self._recorded_authority_process()
        if authority is not None and self._authority_host is not None:
            self._authority_host.stop(authority)
        self._authority_process = None
        result = self._stop_core()
        if result.status in {"stopped", "already_stopped"}:
            self._runtime_record.remove()
        return result

    def status(self) -> RuntimeHealth:
        """Return observed component health with the durable owner-generation receipt."""
        record = self._runtime_record.read()
        if record.owner_lease is None:
            return record
        observed = self._with_authority_process(self._health_probe())
        return RuntimeHealth(
            state=self._runtime_state(observed),
            generation=record.generation,
            owner_lease=record.owner_lease,
            components=observed.components,
            startup_owner_id=record.startup_owner_id,
        )

    def _recorded_authority_process(self) -> Optional[AuthorityProcess]:
        record = self._runtime_record.read()
        for component in record.components:
            if (
                component.component is RuntimeComponent.GODOT_AUTHORITY
                and component.pid is not None
            ):
                return RecordedAuthorityProcess(pid=component.pid)
        return None

    def _wait_for_full_health(self, owner_id: str) -> bool:
        deadline = self._monotonic() + self._authority_timeout_seconds
        while True:
            if not self._startup_claim_matches(owner_id):
                return False
            authority_poll = getattr(self._authority_process, "poll", None)
            if callable(authority_poll) and authority_poll() is not None:
                return False
            if self._runtime_state(self._health_probe()) in {
                RuntimeHealthState.READY,
                RuntimeHealthState.DEGRADED,
            }:
                return True
            if self._monotonic() >= deadline:
                return False
            self._sleeper(0.1)

    def _authority_readiness_failure_detail(self) -> str:
        authority_poll = getattr(self._authority_process, "poll", None)
        if callable(authority_poll):
            exit_code = authority_poll()
            if exit_code is not None:
                return (
                    "Godot authority Runtime exited before readiness "
                    f"(exit code {exit_code})"
                )
        return "Godot authority Runtime did not satisfy the readiness contract before timeout"

    def _cleanup_after_authority_failure(
        self,
        core_result: ServiceLifecycleResult,
        detail: str,
        *,
        owner_id: Optional[str] = None,
    ) -> ServiceLifecycleResult:
        authority = self._authority_process
        if authority is not None and self._authority_host is not None:
            self._authority_host.stop(authority)
        self._authority_process = None
        self._stop_core()
        if owner_id is not None:
            self._clear_starting_record(owner_id)
        self._emit_progress(RuntimeProgressPhase.FAILED)
        return ServiceLifecycleResult(
            status="failed",
            pid=core_result.pid,
            command=core_result.command,
            error=LaunchFailedError(detail),
        )

    def _with_authority_process(self, health: RuntimeHealth) -> RuntimeHealth:
        authority = self._authority_process
        if authority is None:
            return health
        components = tuple(
            ComponentHealth(
                component=component.component,
                state=component.state,
                detail=component.detail,
                pid=authority.pid,
            )
            if component.component is RuntimeComponent.GODOT_AUTHORITY
            else component
            for component in health.components
        )
        return RuntimeHealth(
            state=health.state,
            generation=health.generation,
            owner_lease=health.owner_lease,
            components=components,
            startup_owner_id=health.startup_owner_id,
        )

    def _write_starting_record(
        self, owner_id: str, record_before_start: RuntimeHealth
    ) -> None:
        health = self._with_authority_process(record_before_start)
        if self._authority_process is None:
            health = RuntimeHealth(
                state=health.state,
                generation=health.generation,
                owner_lease=health.owner_lease,
                components=tuple(
                    ComponentHealth(
                        component=component.component,
                        state=component.state,
                        detail=component.detail,
                        pid=None,
                    )
                    if component.component is RuntimeComponent.GODOT_AUTHORITY
                    else component
                    for component in health.components
                ),
                startup_owner_id=health.startup_owner_id,
            )
        self._runtime_record.write(
            RuntimeHealth(
                state=RuntimeHealthState.STARTING,
                generation=record_before_start.generation,
                owner_lease=None,
                components=health.components,
                startup_owner_id=owner_id,
            )
        )

    def _write_starting_record_from_probe(self) -> None:
        record = self._runtime_record.read()
        if (
            record.state is not RuntimeHealthState.STARTING
            or record.startup_owner_id is None
        ):
            return
        self._write_starting_record(record.startup_owner_id, record)

    def _startup_claim_matches(self, owner_id: str) -> bool:
        record = self._runtime_record.read()
        return (
            record.state is RuntimeHealthState.STARTING
            and record.startup_owner_id == owner_id
        )

    def _clear_starting_record(self, owner_id: str) -> None:
        record = self._runtime_record.read()
        if (
            record.startup_owner_id == owner_id
            and record.state is not RuntimeHealthState.STOPPING
        ):
            self._runtime_record.remove()

    def _emit_progress(self, phase: RuntimeProgressPhase) -> None:
        if self._progress_callback is not None:
            self._progress_callback(phase)

    @staticmethod
    def _core_and_gateway_ready(health: RuntimeHealth) -> bool:
        components = {item.component: item.state for item in health.components}
        return all(
            components.get(component) is RuntimeHealthState.READY
            for component in (RuntimeComponent.CORE, RuntimeComponent.GATEWAY)
        )

    @staticmethod
    def _runtime_state(health: RuntimeHealth) -> RuntimeHealthState:
        components = {item.component: item.state for item in health.components}
        required = (
            RuntimeComponent.CORE,
            RuntimeComponent.GATEWAY,
            RuntimeComponent.GODOT_AUTHORITY,
        )
        if any(
            components.get(component) is not RuntimeHealthState.READY
            for component in required
        ):
            return RuntimeHealthState.FAILED
        if components.get(RuntimeComponent.OLLAMA) is RuntimeHealthState.READY:
            return RuntimeHealthState.READY
        return RuntimeHealthState.DEGRADED
