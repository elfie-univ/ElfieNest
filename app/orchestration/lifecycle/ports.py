"""Outbound ports and strict port models owned by Runtime lifecycle orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import (
    Callable,
    ContextManager,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

from pydantic import JsonValue

from app.orchestration.lifecycle.runtime_snapshot import (
    ModelHealthProjection,
    RuntimeSnapshotV1,
)


@dataclass(frozen=True)
class ProcessSnapshot:
    """Stable identity facts observed for one local process."""

    pid: int
    cwd: Path
    command: Tuple[str, ...]
    birth_identity: Optional[str] = None


@dataclass(frozen=True)
class ProcessIdentityEvidence:
    """Exact OS identity used before a managed process can be owned or stopped."""

    pid: int
    executable: str
    birth_identity: str


class ProcessIdentityReaderPort(Protocol):
    """Read PID-reuse-safe process evidence without exposing an OS handle."""

    def read(self, pid: int) -> Optional[ProcessIdentityEvidence]: ...


@dataclass(frozen=True)
class LocalProcessEntry:
    """Technical process-table facts used by local diagnostics."""

    pid: int
    parent_pid: int
    command: Tuple[str, ...]
    cwd: Optional[Path]


@dataclass(frozen=True)
class HttpProbeResult:
    """Minimal HTTP response used by Runtime readiness mapping."""

    status: int
    body: bytes


@dataclass(frozen=True)
class DoctorRepairResult:
    repaired: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DoctorValidationResult:
    passed: bool


@dataclass(frozen=True)
class UninstallState:
    data_home: Path
    home_exists: bool
    config_exists: bool
    env_exists: bool


@dataclass(frozen=True)
class ServicePortStatus:
    """One user-visible loopback service-port observation."""

    port: int
    name: str
    running: bool


@dataclass(frozen=True)
class AuthorityHostConfig:
    """Lifecycle-owned connection and generation inputs for the Godot host."""

    project_root: Path
    http_port: int
    ws_port: int
    nonce: str
    core_pid_file: Optional[Path] = None


class DataHomeState(str, Enum):
    """Read-only classification of the selected product data root."""

    FRESH = "fresh"
    PARTIAL = "partial"
    READY = "ready"
    LEGACY = "legacy"
    CORRUPT = "corrupt"
    PERMISSION = "permission"


@dataclass(frozen=True)
class DataHomeInspection:
    """Safe data-root diagnosis returned before Runtime bootstrap."""

    state: DataHomeState
    home: Path
    detail: str
    recoverable: bool


@dataclass(frozen=True)
class DataHomeRecoveryResult:
    """Result of preserving the old root and activating a fresh root."""

    home: Path
    backup_home: Path


@dataclass(frozen=True)
class SourceCliCandidate:
    """One non-authoritative source checkout candidate for interactive selection."""

    home: Path
    detail: str = ""


@dataclass(frozen=True)
class LifecycleLocalPaths:
    """Resolved lifecycle paths supplied to platform adapters by Bootstrap."""

    home: Path
    logs: Path
    model_validations: Path
    runtime_validations: Path
    runtime_state: Path
    runtime_locks: Path
    source_cli_state: Path


@dataclass(frozen=True)
class RecordedAuthorityProcess:
    """Authority identity recovered from one durable Runtime receipt."""

    pid: int


class AuthorityProcess(Protocol):
    """Minimal owned authority-process identity stored in Runtime receipts."""

    @property
    def pid(self) -> int:
        """Return the exact process or process-group leader identity."""


class ProcessInspectorPort(Protocol):
    """Read local process identity without exposing an OS process object."""

    def exists(self, pid: int) -> bool:
        """Return whether the PID still exists."""

    def cwd(self, pid: int) -> Path:
        """Return the process working directory."""

    def command(self, pid: int) -> Tuple[str, ...]:
        """Return the process command and arguments."""

    def birth_identity(self, pid: int) -> str:
        """Return the OS-provided process start identity."""


class ServiceProcessPort(Protocol):
    """Local process, port and PID-receipt mechanics consumed by lifecycle flows."""

    def exists(self, pid: int) -> bool:
        """Return whether a process identity is live."""

    def inspect(self, pid: int) -> ProcessSnapshot:
        """Read the process working directory and command."""

    def launch(
        self,
        command: Sequence[str],
        cwd: Path,
        *,
        environment: Optional[Mapping[str, str]] = None,
    ) -> int:
        """Launch a detached service process and return its PID."""

    def terminate(self, pid: int, *, force: bool = False) -> None:
        """Signal one process to terminate."""

    def ports_in_use(self, ports: Sequence[int]) -> bool:
        """Return whether any requested loopback port is accepting connections."""

    def port_occupant_pid(self, port: int) -> Optional[int]:
        """Return the first local process occupying a listening port."""

    def current_pid(self) -> int:
        """Return the calling process identity."""

    def list_processes(self) -> Tuple[LocalProcessEntry, ...]:
        """Return the bounded local process-table projection."""

    def read_receipt(self, elfie_home: Path) -> Optional[str]:
        """Read the raw Core PID receipt, or None when absent."""

    def receipt_exists(self, elfie_home: Path) -> bool:
        """Return whether a Core PID receipt exists."""

    def register_receipt(self, elfie_home: Path, pid: int) -> Path:
        """Atomically persist the owned Core PID receipt."""

    def remove_receipt(self, elfie_home: Path, pid: int) -> None:
        """Remove the receipt only when it still belongs to the supplied PID."""

    def clear_receipt(self, elfie_home: Path) -> None:
        """Remove a receipt already classified as stale by an App workflow."""

    def register_current(self, elfie_home: Path) -> Path:
        """Register the calling process and schedule normal-exit cleanup."""

    def retain_current(self) -> None:
        """Retain any platform launch ownership handle for the calling process."""


class LifecycleLease(Protocol):
    """Exclusive startup lease held until the Core PID is registered."""

    def release(self) -> None:
        """Release the lease exactly once."""


class RecoveryLockPort(Protocol):
    """Short cross-process command exclusion for lifecycle state transitions."""

    def acquire_start_lease(
        self, elfie_home: Path, *, blocking: bool = False
    ) -> LifecycleLease:
        """Acquire the service-start lease."""

    def recovery_is_active(self, elfie_home: Path) -> bool:
        """Return whether Owner recovery currently blocks startup."""

    def owner_recovery(self, elfie_home: Path) -> ContextManager[None]:
        """Hold the exclusive Owner recovery lock for one workflow."""


class LifecycleDataHomePort(Protocol):
    """Resolve the production data root for the current command scope."""

    def home(self) -> Path: ...

    def select(
        self,
        explicit_home: Optional[str],
        *,
        project_root: Path,
        runtime_mode: str,
    ) -> Path: ...

    def inspect(self, selected_home: Path) -> DataHomeInspection: ...

    def prepare(self, selected_home: Path) -> DataHomeInspection: ...

    def recover(self, selected_home: Path) -> DataHomeRecoveryResult: ...


class SourceCliStatePort(Protocol):
    """Non-authoritative checkout-scoped history and candidate catalog."""

    def load_history(self) -> Tuple[str, ...]: ...

    def record_history(self, command_line: str) -> bool: ...

    def load_candidates(self) -> Tuple[SourceCliCandidate, ...]: ...

    def record_candidate(self, home: Path, *, detail: str = "") -> None: ...


class LifecycleLocalDataPort(Protocol):
    """Resolve lifecycle-owned local directories without exposing storage code."""

    def paths(self, selected_home: Path) -> LifecycleLocalPaths: ...

    def home(self) -> Path: ...

    def ensure_home(self) -> None: ...

    def logs_dir(self) -> Path: ...

    def model_validation_dir(self) -> Path: ...

    def runtime_validation_dir(self) -> Path: ...

    def runtime_locks_dir(self) -> Path: ...


class DoctorPort(Protocol):
    def repair_local_state(
        self, elfie_home: Optional[Path] = None
    ) -> DoctorRepairResult: ...

    def run_offline_validation(
        self, elfie_home: Optional[Path] = None
    ) -> DoctorValidationResult: ...


class UninstallPort(Protocol):
    def state(self, elfie_home: Optional[Path] = None) -> UninstallState: ...

    def delete_config(self, elfie_home: Optional[Path] = None) -> bool: ...

    def delete_all(self, elfie_home: Optional[Path] = None) -> None: ...


class DesktopProcess(AuthorityProcess, Protocol):
    """Opaque Desktop host process handle used only for lifecycle control."""

    def poll(self) -> Optional[int]:
        """Return the exit code or None while the process is running."""


class DesktopHostPort(Protocol):
    """Packaged Desktop discovery and process mechanics."""

    def find_executable(self, project_root: Path) -> Optional[Path]:
        """Resolve the configured or packaged Desktop executable."""

    def launch(self, command: Sequence[str], cwd: Path) -> DesktopProcess:
        """Launch the Desktop host detached from the calling terminal."""

    def process_id(self, elfie_home: Path) -> Optional[int]:
        """Return the live PID from the Desktop receipt, clearing stale receipts."""

    def write_receipt(self, elfie_home: Path, pid: int) -> None:
        """Persist the Desktop PID receipt."""

    def remove_receipt(self, elfie_home: Path) -> None:
        """Remove the Desktop PID receipt."""

    def exists(self, pid: int) -> bool:
        """Return whether a Desktop PID remains live."""

    def terminate(self, process: DesktopProcess, *, force: bool = False) -> None:
        """Terminate a newly launched Desktop process handle."""

    def wait(self, process: DesktopProcess, *, timeout_seconds: float) -> None:
        """Wait for a newly launched Desktop process to exit."""

    def terminate_pid(self, pid: int) -> None:
        """Terminate a recovered Desktop PID."""


class ControllerIpcPort(Protocol):
    """Authenticated local command client for the packaged Desktop Controller."""

    def request(
        self,
        command: str,
        payload: Optional[Mapping[str, JsonValue]] = None,
    ) -> Optional[Mapping[str, JsonValue]]:
        """Return a Controller response, or None when no Controller is published."""


class HttpProbePort(Protocol):
    """Bounded HTTP GET capability for Runtime readiness probes."""

    def get(self, url: str, *, timeout_seconds: float) -> HttpProbeResult:
        """Return a bounded raw response for App-owned health mapping."""


class RuntimeChannelPort(Protocol):
    """In-process Runtime channel mechanics owned by lifecycle orchestration."""

    def start(self) -> None:
        """Start accepting authenticated Runtime protocol connections."""

    def stop(self) -> None:
        """Stop the channel and release its listening resources."""


class OptionalRuntimeComponentPort(Protocol):
    """Optional local component needed by the full Runtime health projection."""

    def ready(self) -> bool:
        """Return whether the optional component is currently usable."""

    def prepare(self) -> None:
        """Best-effort start of an already configured public installation."""

    def acquire(
        self,
        *,
        owner_id: str,
        instance_id: str,
        generation: int,
        elfie_home: Optional[Path] = None,
    ) -> Optional[LifecycleLease]:
        """Acquire a shared local component lease for one Runtime generation."""

    def reconcile_orphaned_services(
        self, *, elfie_home: Optional[Path] = None
    ) -> tuple[str, ...]:
        """Repair only exact owned services whose Runtime holders disappeared."""


class ModelHealthProjectionPort(Protocol):
    """Read the Food-owned model health projection for one data root."""

    def read(self) -> ModelHealthProjection: ...


class FrontendPreparationPort(Protocol):
    """Prepare source Web artifacts without exposing package-manager mechanics."""

    def prepare(self, runtime_mode: str) -> None: ...


class GodotWebPreparationPort(Protocol):
    """Prepare or verify exported Godot Web artifacts."""

    def prepare(self, runtime_mode: str, *, is_frozen: bool) -> bool: ...


class RuntimeRecordPort(Protocol):
    """Durable authoritative snapshot required by RuntimeSupervisor."""

    def read(self) -> RuntimeSnapshotV1:
        """Read a validated snapshot without repairing or creating state."""

    def initialize_if_fresh(
        self, *, allow_existing_root: bool = False
    ) -> RuntimeSnapshotV1:
        """Create the first snapshot after the root is fresh or prepared."""

    def write(self, snapshot: RuntimeSnapshotV1) -> None:
        """Atomically persist one complete snapshot; OFFLINE is retained."""

    def begin_writer_handoff(
        self, *, generation: int, owner_id: str, recover_stale: bool = False
    ) -> RuntimeWriterHandoff:
        """Issue a generation-scoped credential for the next Core writer.

        ``recover_stale`` is only for a caller that has already proved that
        the recorded Core is absent.  It permits replacing a credential left
        by a crashed generation without weakening normal writer handoff.
        """

    def revoke_writer_handoff(self) -> None:
        """Invalidate the current writer credential after clean shutdown."""


@dataclass(frozen=True)
class RuntimeWriterHandoff:
    """Private parent-to-Core writer credential handoff."""

    token: str
    digest: str
    generation: int
    owner_id: str


class AuthorityHostPort(Protocol):
    """Godot authority-host process mechanics used by RuntimeSupervisor."""

    def start(self) -> Optional[AuthorityProcess]:
        """Start the configured exported authority host."""

    def stop(self, process: AuthorityProcess) -> None:
        """Stop a live or receipt-recovered authority host safely."""


AuthorityHostFactory = Callable[[AuthorityHostConfig], AuthorityHostPort]
RuntimeRecordFactory = Callable[[Path], RuntimeRecordPort]
ModelHealthProjectionFactory = Callable[[Path], ModelHealthProjectionPort]
