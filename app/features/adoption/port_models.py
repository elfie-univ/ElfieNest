"""Typed records crossing Adoption outbound Ports."""

from __future__ import annotations

from dataclasses import dataclass


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


__all__ = (
    "AdoptionPolicyRecord",
    "AdoptionNestCapacityRecord",
    "AdoptionQuotaRecord",
)
