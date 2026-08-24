"""Strict storage and technical observations consumed by Setup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

SetupTaskState = Literal["idle", "running", "failed", "completed", "cancelled"]
SetupOllamaState = Literal[
    "absent",
    "healthy",
    "stopped",
    "deleted",
    "installing",
    "failed",
    "cancelled",
    "repair_required",
]


@dataclass(frozen=True)
class StoredSetupDraft:
    owner_account_id: Optional[str]
    display_name: Optional[str]
    password_hash: Optional[str]
    use_local_ollama: Optional[bool]
    model_id: Optional[str]
    bed_count: Optional[int]
    owner_configured: bool
    offline_configured: bool
    nest_configured: bool
    locked_at: Optional[str]

    @property
    def complete(self) -> bool:
        return (
            self.owner_configured and self.offline_configured and self.nest_configured
        )


@dataclass(frozen=True)
class StoredSetupInstallation:
    owner_user_id: Optional[int]
    status: str
    install_step: Optional[int]
    install_action: Optional[str]
    task_status: SetupTaskState
    task_progress: int
    last_error: Optional[str]
    setup_completed_at: Optional[str]


@dataclass(frozen=True)
class StoredOllamaObservation:
    state: SetupOllamaState
    endpoint: Optional[str]
    version: Optional[str]
    models: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoredSetupModelOption:
    model_id: str
    label: str
    approx_download_mb: int
    recommended: bool


__all__ = (
    "SetupOllamaState",
    "SetupTaskState",
    "StoredOllamaObservation",
    "StoredSetupDraft",
    "StoredSetupInstallation",
    "StoredSetupModelOption",
)
