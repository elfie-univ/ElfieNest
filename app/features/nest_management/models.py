"""Commands and results owned by Nest Management."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateNestBedCountCommand:
    bed_count: int


@dataclass(frozen=True)
class AssignNestHomeCommand:
    elfie_id: str
    home_anchor_id: str | None


@dataclass(frozen=True)
class NestBed:
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
class NestRoom:
    nest_id: str
    name: str
    desired_bed_count: int
    applied_world_revision: int | None
    beds: tuple[NestBed, ...]


@dataclass(frozen=True)
class NestConfiguration:
    desired_bed_count: int
    applied_world_revision: int | None


@dataclass(frozen=True)
class NestBedAssignment:
    elfie_id: str
    home_anchor_id: str | None


__all__ = (
    "AssignNestHomeCommand",
    "NestBed",
    "NestBedAssignment",
    "NestConfiguration",
    "NestRoom",
    "UpdateNestBedCountCommand",
)
