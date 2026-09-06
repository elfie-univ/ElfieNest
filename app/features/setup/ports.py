"""Outbound Ports owned by the Setup Feature."""

from __future__ import annotations

from typing import Literal, Optional, Protocol

from .port_models import (
    StoredOllamaObservation,
    StoredSetupDraft,
    StoredSetupInstallation,
    StoredSetupModelOption,
)


class SetupPortError(RuntimeError):
    pass


class SetupStatePort(Protocol):
    def read_installation(self) -> StoredSetupInstallation: ...

    def read_draft(self) -> StoredSetupDraft: ...

    def save_owner_draft(
        self,
        *,
        account_id: str,
        display_name: Optional[str],
        password_hash: Optional[str],
    ) -> StoredSetupDraft: ...

    def save_offline_draft(
        self, *, use_local_ollama: bool, model_id: Optional[str]
    ) -> StoredSetupDraft: ...

    def save_nest_draft(self, *, bed_count: int) -> StoredSetupDraft: ...

    def save_remote_draft(
        self,
        *,
        configured: bool,
        connection_id: Optional[str],
    ) -> StoredSetupDraft: ...


class SetupOwnerStatusPort(Protocol):
    def has_owner(self) -> bool: ...


class SetupOllamaInspectionPort(Protocol):
    @property
    def platform(self) -> Literal["darwin", "linux", "win32"]: ...

    def inspect(self) -> StoredOllamaObservation: ...


class SetupNestChoicePort(Protocol):
    def validate_bed_count(self, bed_count: int) -> int: ...


class SetupModelCatalogPort(Protocol):
    def list_setup_models(self) -> tuple[StoredSetupModelOption, ...]: ...


__all__ = (
    "SetupOllamaInspectionPort",
    "SetupNestChoicePort",
    "SetupModelCatalogPort",
    "SetupOwnerStatusPort",
    "SetupPortError",
    "SetupStatePort",
)
