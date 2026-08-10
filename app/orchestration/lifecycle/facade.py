"""Stable inbound facade for Runtime lifecycle clients."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, Sequence

from app.orchestration.lifecycle import desktop
from app.orchestration.lifecycle.helpers import existing_service_command, recorded_pid
from app.orchestration.lifecycle.ports import (
    AuthorityHostConfig,
    AuthorityHostFactory,
    DesktopHostPort,
    HttpProbePort,
    HttpProbeResult,
    LifecycleLease,
    LocalProcessEntry,
    ProcessSnapshot,
    RecoveryLockPort,
    RuntimeRecordFactory,
    ServiceProcessPort,
)
from app.orchestration.lifecycle.runtime_health import RuntimeHealth
from app.orchestration.lifecycle.runtime_supervisor import (
    PrepareOptionalComponent,
    RuntimeSupervisor,
)
from app.orchestration.lifecycle.service import start_service, stop_service
from app.orchestration.lifecycle.types import (
    InvalidPidFileError,
    ServiceLifecycleResult,
)


class RuntimeLifecycle(Protocol):
    """Public lifecycle controller returned to inbound clients."""

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        """Start one owned Runtime generation."""

    def status(self) -> RuntimeHealth:
        """Return the latest strict Runtime health snapshot."""

    def stop(self) -> ServiceLifecycleResult:
        """Stop the currently owned Runtime generation."""


class LifecycleFacade:
    """Expose lifecycle workflows without leaking concrete platform adapters."""

    def __init__(
        self,
        *,
        process_port: ServiceProcessPort,
        recovery_lock: RecoveryLockPort,
        desktop_host: DesktopHostPort,
        http_probe: HttpProbePort,
        runtime_record_factory: RuntimeRecordFactory,
        authority_host_factory: AuthorityHostFactory,
    ) -> None:
        self._process_port = process_port
        self._recovery_lock = recovery_lock
        self._desktop_host = desktop_host
        self._http_probe = http_probe
        self._runtime_record_factory = runtime_record_factory
        self._authority_host_factory = authority_host_factory

    def runtime_supervisor(
        self,
        *,
        elfie_home: Path,
        project_root: Path,
        launch_command: Sequence[str],
        authority_config: AuthorityHostConfig,
        health_probe: Callable[[], RuntimeHealth],
        prepare_optional_component: PrepareOptionalComponent = lambda: None,
        authority_timeout_seconds: float = 10.0,
        core_timeout_seconds: float = 10.0,
        child_environment: Optional[Mapping[str, str]] = None,
    ) -> RuntimeLifecycle:
        """Construct the lifecycle workflow from already injected Port factories."""
        command = tuple(launch_command)
        return RuntimeSupervisor(
            runtime_record=self._runtime_record_factory(elfie_home),
            health_probe=health_probe,
            start_core=lambda healthy: self.start_service(
                elfie_home,
                project_root,
                health_checker=healthy,
                command=command,
                timeout_seconds=core_timeout_seconds,
                child_environment=child_environment,
            ),
            stop_core=lambda: self.stop_service(elfie_home, project_root),
            prepare_optional_component=prepare_optional_component,
            owns_pid_record=lambda: self._process_port.receipt_exists(elfie_home),
            authority_host=self._authority_host_factory(authority_config),
            authority_timeout_seconds=authority_timeout_seconds,
        )

    def start_service(
        self,
        elfie_home: Path,
        project_root: Path,
        *,
        health_checker: Callable[[], bool],
        command: Optional[Sequence[str]] = None,
        timeout_seconds: float = 10.0,
        child_environment: Optional[Mapping[str, str]] = None,
    ) -> ServiceLifecycleResult:
        return start_service(
            elfie_home,
            project_root,
            process_port=self._process_port,
            recovery_lock=self._recovery_lock,
            health_checker=health_checker,
            command=command,
            timeout_seconds=timeout_seconds,
            child_environment=child_environment,
        )

    def stop_service(
        self, elfie_home: Path, project_root: Path
    ) -> ServiceLifecycleResult:
        return stop_service(
            elfie_home,
            project_root,
            process_port=self._process_port,
        )

    def start_desktop(
        self,
        elfie_home: Path,
        project_root: Path,
        *,
        health_checker: Callable[[], bool],
        command: Optional[Sequence[str]] = None,
    ) -> ServiceLifecycleResult:
        return desktop.start_desktop_application(
            elfie_home,
            project_root,
            host=self._desktop_host,
            health_checker=health_checker,
            command=command,
        )

    def stop_desktop(self, elfie_home: Path) -> ServiceLifecycleResult:
        return desktop.stop_desktop_application(
            elfie_home,
            host=self._desktop_host,
        )

    def desktop_process_id(self, elfie_home: Path) -> Optional[int]:
        return desktop.desktop_process_id(elfie_home, host=self._desktop_host)

    def http_get(self, url: str, *, timeout_seconds: float) -> HttpProbeResult:
        return self._http_probe.get(url, timeout_seconds=timeout_seconds)

    def process_exists(self, pid: int) -> bool:
        return self._process_port.exists(pid)

    def inspect_process(self, pid: int) -> ProcessSnapshot:
        return self._process_port.inspect(pid)

    def terminate_process(self, pid: int, *, force: bool = False) -> None:
        self._process_port.terminate(pid, force=force)

    def ports_in_use(self, ports: Sequence[int]) -> bool:
        return self._process_port.ports_in_use(ports)

    def port_occupant_pid(self, port: int) -> Optional[int]:
        return self._process_port.port_occupant_pid(port)

    def existing_service_command(
        self, elfie_home: Path, project_root: Path
    ) -> tuple[int, tuple[str, ...]] | None:
        return existing_service_command(elfie_home, project_root, self._process_port)

    def recorded_pid(self, elfie_home: Path) -> int | InvalidPidFileError | None:
        return recorded_pid(elfie_home, self._process_port)

    def receipt_exists(self, elfie_home: Path) -> bool:
        return self._process_port.receipt_exists(elfie_home)

    def clear_receipt(self, elfie_home: Path) -> None:
        self._process_port.clear_receipt(elfie_home)

    def register_current_service(self, elfie_home: Path) -> Path:
        return self._process_port.register_current(elfie_home)

    def current_pid(self) -> int:
        return self._process_port.current_pid()

    def list_processes(self) -> tuple[LocalProcessEntry, ...]:
        return self._process_port.list_processes()

    def acquire_start_lease(
        self, elfie_home: Path, *, blocking: bool = False
    ) -> LifecycleLease:
        return self._recovery_lock.acquire_start_lease(elfie_home, blocking=blocking)

    def owner_recovery(self, elfie_home: Path) -> AbstractContextManager[None]:
        return self._recovery_lock.owner_recovery(elfie_home)

    def service_start_is_blocked(self, elfie_home: Path) -> bool:
        return self._recovery_lock.recovery_is_active(elfie_home)
