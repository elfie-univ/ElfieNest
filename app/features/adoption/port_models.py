"""Typed records crossing Adoption outbound Ports."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ElfieGender, SpeciesId


@dataclass(frozen=True)
class AdoptionPolicyRecord:
    default_elfie_limit: int
    enabled_personality_styles: tuple[str, ...]


@dataclass(frozen=True)
class AdoptionQuotaRecord:
    used: int
    effective_limit: int


@dataclass(frozen=True)
class AdoptionNestCapacityRecord:
    used: int
    maximum: int


@dataclass(frozen=True)
class AdoptionReservationRecord:
    elfie_id: str
    owner_user_id: int
    name: str
    species_id: SpeciesId
    gender: ElfieGender
    birth_date: str
    summary: str
    original_name: str = ""


__all__ = (
    "AdoptionPolicyRecord",
    "AdoptionNestCapacityRecord",
    "AdoptionQuotaRecord",
    "AdoptionReservationRecord",
)
