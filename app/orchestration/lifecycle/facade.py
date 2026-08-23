"""Stable inbound facade for Runtime lifecycle clients."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, Sequence

from pydantic import JsonValue

from app.orchestration.lifecycle import desktop
from app.orchestration.lifecycle.capability_gate import (
    DEFAULT_CAPABILITY_REQUIREMENTS,
    CapabilityPermit,
    CapabilityRequirementRegistry,
)
from app.orchestration.lifecycle.helpers import existing_service_command, recorded_pid
from app.orchestration.lifecycle.ports import (
    AuthorityHostConfig,
    AuthorityHostFactory,
    ControllerIpcPort,
    DataHomeInspection,
    DataHomeRecoveryResult,
    DesktopHostPort,
    DoctorPort,
    DoctorRepairResult,
    DoctorValidationResult,
    FrontendPreparationPort,
    GodotWebPreparationPort,
    HttpProbePort,
    HttpProbeResult,
    LifecycleDataHomePort,
    LifecycleLease,
    LocalProcessEntry,
    ModelHealthProjectionFactory,
    OptionalRuntimeComponentPort,
    ProcessSnapshot,
    RecoveryLockPort,
    RuntimeChannelPort,
    RuntimeRecordFactory,
    RuntimeRecordPort,
    ServicePortStatus,
    ServiceProcessPort,
    SourceCliStatePort,
    UninstallPort,
    UninstallState,
)
from app.orchestration.lifecycle.runtime_snapshot import (
    EndpointSnapshot,
    ModelHealthProjection,
    ModelOverallState,
    RuntimeComponent,
    RuntimeObservation,
    RuntimePhase,
    RuntimeProgressPhase,
    RuntimeProjectionV1,
    RuntimeSnapshotV1,
    RuntimeTarget,
)
from app.orchestration.lifecycle.runtime_supervisor import RuntimeSupervisor
from app.orchestration.lifecycle.service import start_service, stop_service
from app.orchestration.lifecycle.types import (
    DataHomeRecoveryError,
    InvalidPidFileError,
    ServiceLifecycleResult,
    SnapshotRecoveryRequiredError,
)
from app.orchestration.lifecycle.world_worker import RuntimeWorldWorker


class RuntimeLifecycle(Protocol):
    """Public lifecycle controller returned to inbound clients."""

    def start(
        self,
        *,
        owner_id: str,
        desired_target: RuntimeTarget = RuntimeTarget.NORMAL,
        wait_target: RuntimeTarget = RuntimeTarget.CORE,
        correlation_id: Optional[str] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ServiceLifecycleResult:
        """Start one owned Runtime generation."""

    def status(self) -> RuntimeProjectionV1:
        """Return the latest read-only Runtime projection."""

    def recover_owned(
        self,
        *,
        owner_id: str,
        expected_instance_id: str,
        expected_generation: int,
        expected_core_pid: Optional[int],
        health_check: Callable[[], bool],
        correlation_id: Optional[str] = None,
    ) -> ServiceLifecycleResult:
        """Recover one exact lease-scoped generation after revalidation."""

    def stop(self, *, correlation_id: Optional[str] = None) -> ServiceLifecycleResult:
        """Stop the currently owned Runtime generation."""


class LifecycleFacade:
    """Expose lifecycle workflows without leaking concrete platform adapters."""

    def __init__(
        self,
        *,
        service_launch_command: Sequence[str],
        process_port: ServiceProcessPort,
        recovery_lock: RecoveryLockPort,
        desktop_host: DesktopHostPort,
        http_probe: HttpProbePort,
        runtime_record_factory: RuntimeRecordFactory,
        authority_host_factory: AuthorityHostFactory,
        controller_ipc: Optional[ControllerIpcPort] = None,
        optional_component: Optional[OptionalRuntimeComponentPort] = None,
        model_projection_factory: Optional[ModelHealthProjectionFactory] = None,
        frontend_preparation: Optional[FrontendPreparationPort] = None,
        godot_web_preparation: Optional[GodotWebPreparationPort] = None,
        data_home: Optional[LifecycleDataHomePort] = None,
        doctor: Optional[DoctorPort] = None,
        uninstall: Optional[UninstallPort] = None,
        source_cli_state_factory: Optional[Callable[[Path], SourceCliStatePort]] = None,
    ) -> None:
        if not service_launch_command:
            raise ValueError("service_launch_command must not be empty")
        self._service_launch_command = tuple(service_launch_command)
        self._process_port = process_port
        self._recovery_lock = recovery_lock
        self._desktop_host = desktop_host
        self._http_probe = http_probe
        self._runtime_record_factory = runtime_record_factory
        self._authority_host_factory = authority_host_factory
        self._controller_ipc = controller_ipc
        self._optional_component = optional_component
        self._model_projection_factory = model_projection_factory
        self._frontend_preparation = frontend_preparation
        self._godot_web_preparation = godot_web_preparation
        self._data_home = data_home
        self._doctor = doctor
        self._uninstall = uninstall
        self._source_cli_state_factory = source_cli_state_factory

    def default_service_command(
        self, extra_args: Sequence[str] = ()
    ) -> tuple[str, ...]:
        """Build the managed Core command from the Bootstrap-injected target."""
        return (*self._service_launch_command, *extra_args)

    def is_managed_service_command(self, command: Sequence[str]) -> bool:
        """Return whether a process command starts with the injected Core target."""
        target_length = len(self._service_launch_command)
        return tuple(command[:target_length]) == self._service_launch_command

    def prepare_frontend(self, runtime_mode: str) -> None:
        if self._frontend_preparation is None:
            raise RuntimeError("Frontend preparation adapter is unavailable")
        self._frontend_preparation.prepare(runtime_mode)

    def prepare_godot_web(self, runtime_mode: str, *, is_frozen: bool) -> bool:
        if self._godot_web_preparation is None:
            raise RuntimeError("Godot Web preparation adapter is unavailable")
        return self._godot_web_preparation.prepare(
            runtime_mode,
            is_frozen=is_frozen,
        )

    def repair_local_state(
        self, elfie_home: Optional[Path] = None
    ) -> DoctorRepairResult:
        if self._doctor is None:
            raise RuntimeError("Doctor adapter is unavailable")
        base = self._doctor.repair_local_state(elfie_home)
        optional_component = self._optional_component
        if optional_component is None or self._data_home is None:
            return base
        return DoctorRepairResult(
            repaired=(
                *base.repaired,
                *optional_component.reconcile_orphaned_services(
                    elfie_home=elfie_home or self._data_home.home()
                ),
            )
        )

    def run_offline_validation(
        self, elfie_home: Optional[Path] = None
    ) -> DoctorValidationResult:
        if self._doctor is None:
            raise RuntimeError("Doctor adapter is unavailable")
        return self._doctor.run_offline_validation(elfie_home)

    def uninstall_state(self, elfie_home: Optional[Path] = None) -> UninstallState:
        if self._uninstall is None:
            raise RuntimeError("Uninstall adapter is unavailable")
        return self._uninstall.state(elfie_home)

    def delete_local_config(self, elfie_home: Optional[Path] = None) -> bool:
        if self._uninstall is None:
            raise RuntimeError("Uninstall adapter is unavailable")
        return self._uninstall.delete_config(elfie_home)

    def delete_all_local_data(self, elfie_home: Optional[Path] = None) -> None:
        if self._uninstall is None:
            raise RuntimeError("Uninstall adapter is unavailable")
        self._uninstall.delete_all(elfie_home)

    def select_data_home(
        self,
        explicit_home: Optional[str],
        *,
        project_root: Path,
        runtime_mode: str,
    ) -> Path:
        if self._data_home is None:
            raise RuntimeError("Lifecycle data-home adapter is unavailable")
        return self._data_home.select(
            explicit_home,
            project_root=project_root,
            runtime_mode=runtime_mode,
        )

    def source_cli_state(self, source_root: Path) -> SourceCliStatePort:
        """Return optional checkout-scoped convenience state, never product state."""
        if self._source_cli_state_factory is None:
            raise RuntimeError("Source CLI state adapter is unavailable")
        return self._source_cli_state_factory(source_root)

    def inspect_data_home(
        self,
        explicit_home: Optional[str],
        *,
        project_root: Path,
        runtime_mode: str,
    ) -> DataHomeInspection:
        if self._data_home is None:
            raise RuntimeError("Lifecycle data-home adapter is unavailable")
        selected = self._data_home.select(
            explicit_home,
            project_root=project_root,
            runtime_mode=runtime_mode,
        )
        return self._data_home.inspect(selected)

    def prepare_data_home(self, selected_home: Path) -> DataHomeInspection:
        """Prepare the selected root before Runtime snapshot initialization."""
        if self._data_home is None:
            raise RuntimeError("Lifecycle data-home adapter is unavailable")
        try:
            inspection = self._data_home.prepare(selected_home)
        except (OSError, RuntimeError, ValueError) as error:
            raise SnapshotRecoveryRequiredError(selected_home, str(error)) from error
        if inspection.state.value != "ready":
            raise SnapshotRecoveryRequiredError(selected_home, inspection.detail)
        return inspection

    def recover_data_home(
        self,
        explicit_home: Optional[str],
        *,
        project_root: Path,
        runtime_mode: str,
    ) -> DataHomeRecoveryResult:
        if self._data_home is None:
            raise RuntimeError("Lifecycle data-home adapter is unavailable")
        selected = self._data_home.select(
            explicit_home,
            project_root=project_root,
            runtime_mode=runtime_mode,
        )
        with self._recovery_lock.owner_recovery(selected):
            self._assert_data_home_stopped(selected)
            try:
                result = self._data_home.recover(selected)
            except OSError as error:
                raise DataHomeRecoveryError(str(error)) from error
        return result

    def _assert_data_home_stopped(self, selected: Path) -> None:
        """Refuse destructive root replacement when lifecycle evidence is live."""
        snapshot_error: OSError | RuntimeError | ValueError | None
        try:
            snapshot = self._runtime_record_factory(selected).read()
        except (OSError, RuntimeError, ValueError) as error:
            snapshot = None
            snapshot_error = error
        else:
            snapshot_error = None

        if snapshot is not None:
            core = snapshot.component(RuntimeComponent.CORE)
            if core.pid is not None:
                try:
                    if self._process_port.exists(core.pid):
                        raise DataHomeRecoveryError(
                            "Runtime Core is still running; stop it before recovering the data root"
                        )
                except OSError as error:
                    raise DataHomeRecoveryError(
                        f"Cannot verify Runtime Core PID {core.pid}: {error}"
                    ) from error
            if snapshot.phase not in {
                RuntimePhase.OFFLINE,
                RuntimePhase.RECOVERY_REQUIRED,
                RuntimePhase.FAILED,
            }:
                raise DataHomeRecoveryError(
                    f"Runtime is in {snapshot.phase.value}; stop it before recovering the data root"
                )

        if snapshot_error is not None and self._process_port.receipt_exists(selected):
            raise DataHomeRecoveryError(
                f"Runtime snapshot cannot be verified: {snapshot_error}; "
                "ensure the task is stopped before recovering the data root"
            )

        if not self._process_port.receipt_exists(selected):
            return
        try:
            pid_result = recorded_pid(selected, self._process_port)
        except OSError as error:
            raise DataHomeRecoveryError(
                f"Cannot read the Runtime PID receipt: {error}"
            ) from error
        if isinstance(pid_result, InvalidPidFileError):
            raise DataHomeRecoveryError(
                "Runtime PID receipt is invalid; ensure the task is stopped "
                "before recovering the data root"
            )
        if pid_result is None:
            raise DataHomeRecoveryError(
                "Runtime PID receipt disappeared during recovery validation; retry"
            )
        try:
            receipt_live = self._process_port.exists(pid_result)
        except OSError as error:
            raise DataHomeRecoveryError(
                f"Cannot verify Runtime PID {pid_result}: {error}"
            ) from error
        if receipt_live:
            raise DataHomeRecoveryError(
                f"Runtime PID {pid_result} is still running; stop it before recovering the data root"
            )

    def optional_component_ready(self) -> bool:
        """Project optional Runtime readiness without exposing its technology."""
        return (
            False
            if self._optional_component is None
            else self._optional_component.ready()
        )

    def prepare_optional_component(self) -> None:
        """Best-effort prepare the injected optional Runtime component."""
        if self._optional_component is not None:
            self._optional_component.prepare()

    def acquire_optional_component_lease(
        self,
        *,
        owner_id: str,
        instance_id: str,
        generation: int,
        elfie_home: Optional[Path] = None,
    ) -> Optional[LifecycleLease]:
        """Acquire the optional component lease without exposing its technology."""
        if self._optional_component is None:
            return None
        acquire = getattr(self._optional_component, "acquire", None)
        if not callable(acquire):
            return None
        return acquire(
            owner_id=owner_id,
            instance_id=instance_id,
            generation=generation,
            elfie_home=elfie_home,
        )

    def runtime_snapshot(self, elfie_home: Path) -> RuntimeSnapshotV1:
        """Read the authoritative snapshot for a Core-resident handoff."""
        return self._runtime_record_factory(elfie_home).read()

    def publish_core_endpoints(
        self,
        elfie_home: Path,
        endpoints: Sequence[EndpointSnapshot],
    ) -> None:
        """Publish Core-owned endpoints before the readiness probe runs.

        The managed Core receives the generation writer credential from the
        Supervisor. This small handoff lets automatic sockets be selected and
        reserved inside Core while keeping the durable Runtime snapshot as the
        only endpoint authority visible to clients.
        """
        record = self._runtime_record_factory(elfie_home)
        current = record.read()
        if current.phase is not RuntimePhase.CORE_STARTING:
            raise RuntimeError(
                "Core endpoints may only be published during CORE_STARTING"
            )
        record.write(
            replace(
                current,
                revision=current.revision + 1,
                endpoints=tuple(endpoints),
            )
        )

    def runtime_projection(self, elfie_home: Path) -> RuntimeProjectionV1:
        """Return the read-only snapshot plus the current Food model projection.

        The durable Runtime record remains the only lifecycle fact source.  The
        model fields are overlaid from Food's persisted evidence exactly as the
        capability gate does; this method does not start services or perform a
        live inference check.
        """
        snapshot = self.runtime_snapshot(elfie_home)
        model = self.model_health_projection(elfie_home)
        return replace(
            snapshot.projection(),
            model_state=model.state,
            model_common_state=model.common_state,
            model_emergency_state=model.emergency_state,
            model_revision=model.revision,
        )

    def issue_capability_permit(
        self,
        elfie_home: Path,
        operation: str,
        *,
        registry: CapabilityRequirementRegistry = DEFAULT_CAPABILITY_REQUIREMENTS,
    ) -> CapabilityPermit:
        """Issue a revision-bound permit without starting or probing anything."""
        return registry.issue(operation, self.runtime_projection(elfie_home))

    def model_health_projection(self, elfie_home: Path) -> ModelHealthProjection:
        """Read the Food-owned model projection without performing validation."""
        if self._model_projection_factory is None:
            optional_ready = self.optional_component_ready()
            return ModelHealthProjection(
                state=(
                    ModelOverallState.READY
                    if optional_ready
                    else ModelOverallState.DEGRADED
                ),
                common_state=(
                    ModelOverallState.READY
                    if optional_ready
                    else ModelOverallState.DEGRADED
                ),
                emergency_state=(
                    ModelOverallState.READY
                    if optional_ready
                    else ModelOverallState.UNAVAILABLE
                ),
            )
        return self._model_projection_factory(elfie_home).read()

    def runtime_supervisor(
        self,
        *,
        elfie_home: Path,
        project_root: Path,
        launch_command: Sequence[str],
        authority_config: AuthorityHostConfig,
        health_probe: Callable[[], RuntimeObservation],
        authority_timeout_seconds: float = 10.0,
        core_timeout_seconds: float = 10.0,
        child_environment: Optional[Mapping[str, str]] = None,
        progress_callback: Optional[Callable[[RuntimeProgressPhase], None]] = None,
    ) -> RuntimeLifecycle:
        """Construct the lifecycle workflow from already injected Port factories."""
        command = tuple(launch_command)
        environment = dict(child_environment or {})
        runtime_record = self._runtime_record_factory(elfie_home)

        def _prepare_data_home() -> None:
            self.prepare_data_home(elfie_home)

        def _stop_core() -> ServiceLifecycleResult:
            # start_service owns cleanup until it has published the Core
            # identity.  Do not ask the snapshot-bound stop path to invent a
            # PID for a launch that failed before CORE_READY.
            if runtime_record.read().component(RuntimeComponent.CORE).pid is None:
                return ServiceLifecycleResult(status="already_stopped")
            return self.stop_service(elfie_home, project_root)

        return RuntimeSupervisor(
            runtime_record=runtime_record,
            prepare_data_home=_prepare_data_home,
            health_probe=health_probe,
            start_core=lambda healthy: self.start_service(
                elfie_home,
                project_root,
                health_checker=healthy,
                command=command,
                timeout_seconds=core_timeout_seconds,
                child_environment=environment,
                runtime_record=runtime_record,
            ),
            stop_core=_stop_core,
            owns_pid_record=lambda: (
                existing_service_command(
                    elfie_home,
                    project_root,
                    self._process_port,
                    runtime_record=runtime_record,
                    expected_command=self._service_launch_command,
                )
                is not None
            ),
            # Godot is owned by the Core-resident World worker. The launcher
            # may wait for its published WORLD_READY snapshot but must not
            # start a second authority process itself.
            authority_host=None,
            authority_recovery_host=self._authority_host_factory(authority_config),
            authority_timeout_seconds=authority_timeout_seconds,
            progress_callback=progress_callback,
            command_lease_factory=lambda: self._recovery_lock.acquire_start_lease(
                elfie_home
            ),
            core_process_identity=self._process_port.inspect,
            core_process_exists=self._process_port.exists,
            model_projection_probe=lambda: self.model_health_projection(elfie_home),
            child_environment=environment,
        )

    def runtime_world_worker(
        self,
        *,
        elfie_home: Path,
        authority_config: AuthorityHostConfig,
        world_ready_probe: Callable[[], bool],
        authority_timeout_seconds: float = 120.0,
    ) -> RuntimeWorldWorker:
        """Build the Core-resident World convergence worker."""
        return RuntimeWorldWorker(
            runtime_record=self._runtime_record_factory(elfie_home),
            authority_host=self._authority_host_factory(authority_config),
            world_ready_probe=world_ready_probe,
            authority_timeout_seconds=authority_timeout_seconds,
            command_lease_factory=lambda: self._recovery_lock.acquire_start_lease(
                elfie_home
            ),
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
        runtime_record: Optional[RuntimeRecordPort] = None,
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
            runtime_record=runtime_record,
        )

    def stop_service(
        self, elfie_home: Path, project_root: Path
    ) -> ServiceLifecycleResult:
        return stop_service(
            elfie_home,
            project_root,
            process_port=self._process_port,
            expected_command=self._service_launch_command,
            runtime_record=self._runtime_record_factory(elfie_home),
        )

    def start_desktop(
        self,
        elfie_home: Path,
        project_root: Path,
        *,
        health_checker: Callable[[], bool],
        command: Optional[Sequence[str]] = None,
        background: bool = False,
        timeout_seconds: float = 30.0,
    ) -> ServiceLifecycleResult:
        return desktop.start_desktop_application(
            elfie_home,
            project_root,
            host=self._desktop_host,
            health_checker=health_checker,
            command=command,
            background=background,
            timeout_seconds=timeout_seconds,
        )

    def stop_desktop(self, elfie_home: Path) -> ServiceLifecycleResult:
        return desktop.stop_desktop_application(
            elfie_home,
            host=self._desktop_host,
        )

    def controller_request(
        self,
        command: str,
        payload: Optional[Mapping[str, JsonValue]] = None,
        *,
        expected_data_home: Optional[Path] = None,
    ) -> Optional[Mapping[str, JsonValue]]:
        """Send one authenticated local command without owning Controller state."""
        if self._controller_ipc is None:
            return None
        if expected_data_home is not None:
            merged_payload = dict(payload or {})
            merged_payload["expected_data_home"] = str(expected_data_home.resolve())
            payload = merged_payload
        return self._controller_ipc.request(command, payload)

    def desktop_process_id(self, elfie_home: Path) -> Optional[int]:
        return desktop.desktop_process_id(elfie_home, host=self._desktop_host)

    def http_get(self, url: str, *, timeout_seconds: float) -> HttpProbeResult:
        return self._http_probe.get(url, timeout_seconds=timeout_seconds)

    def start_runtime_channel(self, channel: RuntimeChannelPort) -> None:
        """Start the in-process Runtime channel through the lifecycle owner."""
        channel.start()

    def stop_runtime_channel(self, channel: RuntimeChannelPort) -> None:
        """Stop the in-process Runtime channel through the lifecycle owner."""
        channel.stop()

    def process_exists(self, pid: int) -> bool:
        return self._process_port.exists(pid)

    def inspect_process(self, pid: int) -> ProcessSnapshot:
        return self._process_port.inspect(pid)

    def terminate_process(self, pid: int, *, force: bool = False) -> None:
        self._process_port.terminate(pid, force=force)

    def ports_in_use(self, ports: Sequence[int]) -> bool:
        return self._process_port.ports_in_use(ports)

    def default_port_statuses(self) -> tuple[ServicePortStatus, ...]:
        return self.service_port_statuses(8000)

    def service_port_statuses(
        self,
        http_port: int,
        godot_ws_port: int = 8765,
    ) -> tuple[ServicePortStatus, ...]:
        return tuple(
            ServicePortStatus(
                port=port,
                name=name,
                running=self._process_port.ports_in_use((port,)),
            )
            for port, name in (
                (http_port, "HTTP"),
                (godot_ws_port, "WebSocket (Godot)"),
            )
        )

    def port_occupant_pid(self, port: int) -> Optional[int]:
        return self._process_port.port_occupant_pid(port)

    def existing_service_command(
        self, elfie_home: Path, project_root: Path
    ) -> tuple[int, tuple[str, ...]] | None:
        return existing_service_command(
            elfie_home,
            project_root,
            self._process_port,
            runtime_record=self._runtime_record_factory(elfie_home),
            expected_command=self._service_launch_command,
        )

    def recorded_pid(self, elfie_home: Path) -> int | InvalidPidFileError | None:
        return recorded_pid(elfie_home, self._process_port)

    def receipt_exists(self, elfie_home: Path) -> bool:
        return self._process_port.receipt_exists(elfie_home)

    def clear_receipt(self, elfie_home: Path) -> None:
        self._process_port.clear_receipt(elfie_home)

    def register_current_service(self, elfie_home: Path) -> Path:
        return self._process_port.register_current(elfie_home)

    def retain_current_service_process(self) -> None:
        self._process_port.retain_current()

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
