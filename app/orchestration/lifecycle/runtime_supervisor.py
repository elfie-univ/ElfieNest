"""Component-aware façade over the established Core lifecycle primitives."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Optional, Protocol

from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    OwnerLease,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
)
from app.orchestration.lifecycle.types import LaunchFailedError, ServiceLifecycleResult
from godot_runtime.launcher import AuthorityLaunchError

RUNTIME_RECORD_FILENAME: Final = "runtime.json"
HealthProbe = Callable[[], RuntimeHealth]
StartCore = Callable[[Callable[[], bool]], ServiceLifecycleResult]
StopCore = Callable[[], ServiceLifecycleResult]
PrepareOptionalComponent = Callable[[], None]
OwnedRecord = Callable[[], bool]


class AuthorityProcess(Protocol):
    """Minimal owned authority-process identity used in Runtime receipts."""

    @property
    def pid(self) -> int:
        """Return the exact process or process-group leader identity."""


AuthorityStarter = Callable[[], Optional[AuthorityProcess]]
AuthorityStopper = Callable[[AuthorityProcess], None]


@dataclass(frozen=True)
class _RecordedAuthorityProcess:
    """Authority identity recovered from this generation's private receipt."""

    pid: int


class RuntimeSupervisor:
    """Own the Core process while reporting the complete Runtime component graph."""

    def __init__(
        self,
        *,
        elfie_home: Path,
        project_root: Path,
        health_probe: HealthProbe,
        start_core: StartCore,
        stop_core: StopCore,
        prepare_optional_component: PrepareOptionalComponent = lambda: None,
        owns_pid_record: OwnedRecord = lambda: True,
        start_authority: Optional[AuthorityStarter] = None,
        stop_authority: Optional[AuthorityStopper] = None,
        authority_timeout_seconds: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._elfie_home = elfie_home
        self._project_root = project_root
        self._health_probe = health_probe
        self._start_core = start_core
        self._stop_core = stop_core
        self._prepare_optional_component = prepare_optional_component
        self._owns_pid_record = owns_pid_record
        self._start_authority = start_authority
        self._stop_authority = stop_authority
        self._authority_timeout_seconds = authority_timeout_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._authority_process: Optional[AuthorityProcess] = None

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        """Start Core once and persist its full component-generation receipt."""
        record_before_start = self._read_record()
        health_before_start = self._health_probe()
        self._prepare_optional_component()
        result = self._start_core(
            lambda: self._core_and_gateway_ready(self._health_probe())
        )
        if result.status not in {"started", "already_running"}:
            failed_health = self._health_probe()
            self._write_record(
                RuntimeHealth(
                    state=self._runtime_state(failed_health),
                    generation=self._read_record().generation,
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
        if self._start_authority is not None:
            try:
                authority = self._start_authority()
            except AuthorityLaunchError as error:
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
        health = self._health_probe()
        health = self._with_authority_process(health)
        state = self._runtime_state(health)
        record = self._read_record()
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
        self._write_record(complete)
        return result

    def stop(self) -> ServiceLifecycleResult:
        """Stop owned Core first; public Ollama is deliberately never signalled."""
        authority = self._authority_process or self._recorded_authority_process()
        if authority is not None and self._stop_authority is not None:
            self._stop_authority(authority)
        self._authority_process = None
        result = self._stop_core()
        if result.status in {"stopped", "already_stopped"}:
            self._record_path().unlink(missing_ok=True)
        return result

    def _recorded_authority_process(self) -> Optional[AuthorityProcess]:
        record = self._read_record()
        for component in record.components:
            if (
                component.component is RuntimeComponent.GODOT_AUTHORITY
                and component.pid is not None
            ):
                return _RecordedAuthorityProcess(pid=component.pid)
        return None

    def status(self) -> RuntimeHealth:
        """Return current component health with the durable owner-generation receipt."""
        record = self._read_record()
        if record.owner_lease is None:
            return record
        observed = self._health_probe()
        observed = self._with_authority_process(observed)
        return RuntimeHealth(
            state=self._runtime_state(observed),
            generation=record.generation,
            owner_lease=record.owner_lease,
            components=observed.components,
        )

    def _record_path(self) -> Path:
        return self._elfie_home / RUNTIME_RECORD_FILENAME

    def _read_record(self) -> RuntimeHealth:
        try:
            payload = json.loads(self._record_path().read_text(encoding="utf-8"))
            generation = payload["generation"]
            owner_id = payload.get("owner_id")
            state = RuntimeHealthState(payload["state"])
            raw_components = payload["components"]
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
            return RuntimeHealth(
                state=RuntimeHealthState.STOPPED,
                generation=0,
                owner_lease=None,
                components=(),
            )
        if not isinstance(generation, int) or generation < 0:
            return RuntimeHealth(
                state=RuntimeHealthState.FAILED,
                generation=0,
                owner_lease=None,
                components=(),
            )
        components: list[ComponentHealth] = []
        try:
            for raw_component in raw_components:
                components.append(
                    ComponentHealth(
                        component=RuntimeComponent(raw_component["component"]),
                        state=RuntimeHealthState(raw_component["state"]),
                        detail=raw_component.get("detail", ""),
                        pid=raw_component.get("pid"),
                    )
                )
        except (KeyError, TypeError, ValueError):
            return RuntimeHealth(
                state=RuntimeHealthState.FAILED,
                generation=0,
                owner_lease=None,
                components=(),
            )
        owner_lease = (
            OwnerLease(owner_id=owner_id, generation=generation)
            if isinstance(owner_id, str) and generation > 0
            else None
        )
        return RuntimeHealth(
            state=state,
            generation=generation,
            owner_lease=owner_lease,
            components=tuple(components),
        )

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
        if authority is not None and self._stop_authority is not None:
            self._stop_authority(authority)
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

    def _write_record(self, health: RuntimeHealth) -> None:
        self._elfie_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".runtime.", dir=str(self._elfie_home)
        )
        temporary_path = Path(temporary_name)
        payload = json.dumps(
            {
                "generation": health.generation,
                "owner_id": health.owner_lease.owner_id if health.owner_lease else "",
                "state": health.state.value,
                "components": [
                    {
                        "component": component.component.value,
                        "state": component.state.value,
                        "detail": component.detail,
                        "pid": component.pid,
                    }
                    for component in health.components
                ],
            },
            sort_keys=True,
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as receipt:
                receipt.write(payload)
            temporary_path.replace(self._record_path())
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise

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
