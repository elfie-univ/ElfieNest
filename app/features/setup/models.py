"""Commands, queries and results owned by first-run Setup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .port_models import SetupOllamaState, SetupTaskState


@dataclass(frozen=True)
class SetupPrincipal:
    kind: Literal["setup", "owner"]
    local: bool


@dataclass(frozen=True)
class GetSetupStatusQuery:
    pass


@dataclass(frozen=True)
class ListSetupModelsQuery:
    pass


@dataclass(frozen=True)
class InspectSetupOllamaQuery:
    pass


@dataclass(frozen=True)
class SaveSetupOwnerDraftCommand:
    account_id: str
    display_name: Optional[str]
    password: Optional[str]


@dataclass(frozen=True)
class SaveSetupOfflineDraftCommand:
    use_local_ollama: bool
    model_id: Optional[str]


@dataclass(frozen=True)
class SaveSetupNestDraftCommand:
    bed_count: int


@dataclass(frozen=True)
class SaveSetupRemoteDraftCommand:
    configured: bool
    connection_id: Optional[str]


@dataclass(frozen=True)
class SetupModelOptionResult:
    model_id: str
    label: str
    approx_download_mb: int
    recommended: bool


@dataclass(frozen=True)
class SetupDraftResult:
    owner_account_id: Optional[str]
    display_name: Optional[str]
    password_configured: bool
    use_local_ollama: Optional[bool]
    ollama_installed: bool
    model_id: Optional[str]
    bed_count: Optional[int]
    owner_configured: bool
    offline_configured: bool
    nest_configured: bool
    locked_at: Optional[str]
    remote_configured: bool
    remote_skipped: bool
    remote_connection_id: Optional[str]


@dataclass(frozen=True)
class SetupStepResult:
    number: int
    name: str
    status: Literal["pending", "current", "completed"]
    retry_action: Optional[str]


@dataclass(frozen=True)
class SetupInstallResult:
    phase: Literal["model_validation", "common_food", "nest", "runtime"]
    action_key: str
    state: SetupTaskState
    progress: int
    error_key: Optional[str]


@dataclass(frozen=True)
class SetupStatusResult:
    need_setup: bool
    complete: bool
    current_step: int
    steps: tuple[SetupStepResult, ...]
    last_error: Optional[str]
    draft: SetupDraftResult
    install: SetupInstallResult
    locked: bool


@dataclass(frozen=True)
class SetupOllamaResult:
    state: SetupOllamaState
    endpoint: Optional[str]
    version: Optional[str]
    platform: Literal["darwin", "linux", "win32"]


__all__ = tuple(
    name for name in globals() if name.endswith(("Command", "Query", "Result"))
) + ("SetupPrincipal",)
