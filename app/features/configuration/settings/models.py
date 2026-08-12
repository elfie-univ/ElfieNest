"""Commands, queries and results owned by global product Settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .port_models import SpeciesId


@dataclass(frozen=True)
class GetElfieSettingsQuery:
    pass


@dataclass(frozen=True)
class GetRuntimeSettingsQuery:
    pass


@dataclass(frozen=True)
class GetSecuritySettingsQuery:
    pass


@dataclass(frozen=True)
class UpdateElfieSettingsCommand:
    max_elfies_per_user: Optional[int] = None
    allowed_species_ids: Optional[Tuple[SpeciesId, ...]] = None
    personality_presets_enabled: Optional[Tuple[Tuple[str, bool], ...]] = None


@dataclass(frozen=True)
class UpdateRuntimeSettingsCommand:
    tick_interval_sec: Optional[float] = None


@dataclass(frozen=True)
class LoginRateLimit:
    max_attempts: int
    window_seconds: int


@dataclass(frozen=True)
class UpdateSecuritySettingsCommand:
    session_ttl_days: Optional[int] = None
    rate_limit: Optional[LoginRateLimit] = None


@dataclass(frozen=True)
class ResetSettingsCommand:
    pass


@dataclass(frozen=True)
class ElfieSettingsResult:
    max_elfies_per_user: int
    allowed_species_ids: Tuple[SpeciesId, ...]
    personality_presets_enabled: Tuple[Tuple[str, bool], ...]


@dataclass(frozen=True)
class RuntimeSettingsResult:
    tick_interval_sec: float


@dataclass(frozen=True)
class SecuritySettingsResult:
    session_ttl_days: int
    rate_limit: LoginRateLimit


@dataclass(frozen=True)
class SettingsResetResult:
    elfies: ElfieSettingsResult
    runtime: RuntimeSettingsResult
    security: SecuritySettingsResult


__all__ = (
    "ElfieSettingsResult",
    "GetElfieSettingsQuery",
    "GetRuntimeSettingsQuery",
    "GetSecuritySettingsQuery",
    "LoginRateLimit",
    "ResetSettingsCommand",
    "RuntimeSettingsResult",
    "SecuritySettingsResult",
    "SettingsResetResult",
    "UpdateElfieSettingsCommand",
    "UpdateRuntimeSettingsCommand",
    "UpdateSecuritySettingsCommand",
)
