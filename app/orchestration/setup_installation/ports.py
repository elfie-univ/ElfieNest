"""Consumer-owned Ports for the resumable Setup installation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional, Protocol

from app.features.setup import StoredSetupDraft, StoredSetupInstallation


@dataclass(frozen=True)
class CreatedSetupOwner:
    user_id: int
    account_id: str
    display_name: Optional[str]


@dataclass(frozen=True)
class SetupOllamaBinding:
    api_base: str
    platform: Literal["darwin", "linux", "win32"]
    install_kind: str
    launch_target: str
    version: str
    installer_source_url: str = ""
    installer_sha256: str = ""


@dataclass(frozen=True)
class SetupOllamaProbe:
    state: Literal[
        "absent",
        "healthy",
        "stopped",
        "deleted",
        "installing",
        "failed",
        "cancelled",
        "repair_required",
    ]
    endpoint: str
    version: Optional[str] = None


@dataclass(frozen=True)
class SetupDownloadedInstaller:
    source_url: str
    sha256: str
    script_path: Path
    command: tuple[str, ...]


class SetupInstallationPortError(RuntimeError):
    pass


@dataclass(frozen=True)
class SetupModelValidationResult:
    """Persisted Provider evidence projected for the Setup progress view."""

    total: int
    passed: int


class SetupRemotePreparationPort(Protocol):
    """Run the full remote preparation work after Setup is locked."""

    def validate_models(
        self,
        owner: CreatedSetupOwner,
        connection_id: str,
    ) -> SetupModelValidationResult: ...

    def prepare_common_food(
        self,
        owner: CreatedSetupOwner,
        connection_id: str,
    ) -> None: ...


class SetupRuntimeReadinessPort(Protocol):
    """Wait for the already-managed Nest Runtime to become usable."""

    def ensure_ready(self, cancelled: Callable[[], bool]) -> None: ...


class SetupInstallationStatePort(Protocol):
    def read_installation(self) -> StoredSetupInstallation: ...
    def read_draft(self) -> StoredSetupDraft: ...
    def lock_draft(self) -> StoredSetupDraft: ...
    def mark_owner_completed(self, user_id: int) -> None: ...
    def begin_or_resume(self) -> StoredSetupInstallation: ...
    def report(self, *, phase: int, action_key: str, progress: int) -> None: ...
    def complete_phase(self, phase: int) -> StoredSetupInstallation: ...
    def fail(self, action_key: str, error: str) -> None: ...
    def cancel_installation(self) -> StoredSetupInstallation: ...
    def recover_running(self, error: str) -> None: ...


class SetupAccountPort(Protocol):
    def find_owner(self) -> CreatedSetupOwner | None: ...

    def create_first_owner(self, draft: StoredSetupDraft) -> CreatedSetupOwner: ...
    def issue_session(self, user_id: int) -> tuple[str, int]: ...

    def set_default_landing_page(
        self, user_id: int, page: Literal["chat", "manage"]
    ) -> None: ...


class SetupOllamaInstallPort(Protocol):
    def ensure_installation(
        self, report: Callable[[str], None]
    ) -> Optional[SetupOllamaTaskLease]: ...
    def ensure_model(self, model_id: str, report: Callable[[str], None]) -> str: ...


class SetupOllamaTaskLease(Protocol):
    """A short-lived lease held while Setup mutates the local model service."""

    def release(self) -> None: ...


SetupOllamaTaskLeaseFactory = Callable[[], Optional[SetupOllamaTaskLease]]


class SetupProviderPort(Protocol):
    def configured_model_reference(self, model_id: str) -> Optional[str]: ...


class SetupFoodPort(Protocol):
    def ensure_emergency_food(self, model_reference: str) -> None: ...


class SetupNestPort(Protocol):
    def initialize_bed_count(self, bed_count: int) -> None: ...


class SetupInstallationRunnerPort(Protocol):
    def start(
        self,
        key: str,
        worker: Callable[[Callable[[], bool]], None],
        *,
        timeout_seconds: float,
        on_timeout: Callable[[], None],
    ) -> bool: ...

    def cancel(self, key: str) -> bool: ...


__all__ = (
    "CreatedSetupOwner",
    "SetupAccountPort",
    "SetupDownloadedInstaller",
    "SetupFoodPort",
    "SetupInstallationPortError",
    "SetupInstallationRunnerPort",
    "SetupInstallationStatePort",
    "SetupModelValidationResult",
    "SetupNestPort",
    "SetupOllamaBinding",
    "SetupOllamaProbe",
    "SetupOllamaInstallPort",
    "SetupOllamaTaskLease",
    "SetupOllamaTaskLeaseFactory",
    "SetupProviderPort",
    "SetupRemotePreparationPort",
    "SetupRuntimeReadinessPort",
)
