"""Typed models crossing the Settings persistence Port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

from typing_extensions import TypeAlias

SpeciesId: TypeAlias = Literal["dog", "fox", "cat"]


@dataclass(frozen=True)
class StoredElfieSettings:
    max_elfies_per_user: int
    allowed_species_ids: Tuple[SpeciesId, ...]
    personality_presets_enabled: Tuple[Tuple[str, bool], ...]


@dataclass(frozen=True)
class StoredRuntimeSettings:
    tick_interval_sec: float


@dataclass(frozen=True)
class StoredLoginRateLimit:
    max_attempts: int
    window_seconds: int


@dataclass(frozen=True)
class StoredSecuritySettings:
    session_ttl_days: int
    rate_limit: StoredLoginRateLimit


__all__ = (
    "StoredElfieSettings",
    "StoredLoginRateLimit",
    "StoredRuntimeSettings",
    "StoredSecuritySettings",
    "SpeciesId",
)
