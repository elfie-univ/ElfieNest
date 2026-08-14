"""Persistence boundary consumed by Nest Management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NestBedRecord:
    anchor_id: str
    label: str
    order: int
    occupant_id: str | None
    occupant_name: str | None
    occupant_owner_user_id: int | None
    occupant_species_id: str | None
    occupant_owner_account_id: str | None
    occupant_owner_display_name: str | None


@dataclass(frozen=True)
class NestSnapshotRecord:
    desired_bed_count: int
    applied_world_revision: int | None
    beds: tuple[NestBedRecord, ...]


class NestPortError(RuntimeError):
    """The technical Nest Management boundary could not complete an operation."""


class NestPortConflict(NestPortError):
    """The requested mutation conflicts with persisted Nest facts."""


class NestPortResidentNotFound(NestPortError):
    """The requested Elfie is not a persisted Nest resident."""


class NestPortBedNotFound(NestPortError):
    """The requested semantic bed does not exist in the configured Nest."""


class NestManagementPort(Protocol):
    def load_snapshot(self) -> NestSnapshotRecord: ...

    def update_bed_count(self, bed_count: int) -> NestSnapshotRecord: ...

    def assign_home(self, elfie_id: str, home_anchor_id: str | None) -> None: ...


__all__ = (
    "NestBedRecord",
    "NestManagementPort",
    "NestPortBedNotFound",
    "NestPortConflict",
    "NestPortError",
    "NestPortResidentNotFound",
    "NestSnapshotRecord",
)
