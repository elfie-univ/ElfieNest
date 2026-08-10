"""Component-aware Runtime lifecycle workflow."""

from __future__ import annotations

import time
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
        self._authority_process: Optional[AuthorityProcess] = None

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        """Start Core once and persist its full component-generation receipt."""
        record_before_start = self._runtime_record.read()
        health_before_start = self._health_probe()
        self._prepare_optional_component()
        result = self._start_core(
            lambda: self._core_and_gateway_ready(self._health_probe())
        )
        if result.status not in {"started", "already_running"}:
            failed_health = self._health_probe()
            self._runtime_record.write(
                RuntimeHealth(
                    state=self._runtime_state(failed_health),
                    generation=self._runtime_record.read().generation,
                    owner_lease=None,
                    components=failed_health.components,
                )
            )
            return result
        if not self._owns_pid_record():
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
                authority = self._authority_host.start()
            except AuthorityHostError as error:
                return self._cleanup_after_authority_failure(result, str(error))
            if authority is None:
                return self._cleanup_after_authority_failure(
                    result, "Godot authority Runtime failed to start"
                )
            self._authority_process = authority
            if not self._wait_for_full_health():
                return self._cleanup_after_authority_failure(
                    result,
                    "Godot authority Runtime did not satisfy the readiness contract before timeout",
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
        )
        self._runtime_record.write(complete)
        return result

    def stop(self) -> ServiceLifecycleResult:
        """Stop the owned authority and Core; public Ollama is never signalled."""
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

    def _wait_for_full_health(self) -> bool:
        deadline = self._monotonic() + self._authority_timeout_seconds
        while True:
            if self._runtime_state(self._health_probe()) in {
                RuntimeHealthState.READY,
                RuntimeHealthState.DEGRADED,
            }:
                return True
            if self._monotonic() >= deadline:
                return False
            self._sleeper(0.1)

    def _cleanup_after_authority_failure(
        self,
        core_result: ServiceLifecycleResult,
        detail: str,
    ) -> ServiceLifecycleResult:
        authority = self._authority_process
        if authority is not None and self._authority_host is not None:
            self._authority_host.stop(authority)
        self._authority_process = None
        self._stop_core()
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
        )

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
