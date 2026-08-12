"""Global Settings use-cases over a typed, atomic settings Port."""

from __future__ import annotations

from typing import Final

from app.features.accounts import AccountPrincipal

from .errors import SettingsForbidden, SettingsValidationError
from .models import (
    ElfieSettingsResult,
    GetElfieSettingsQuery,
    GetRuntimeSettingsQuery,
    GetSecuritySettingsQuery,
    LoginRateLimit,
    ResetSettingsCommand,
    RuntimeSettingsResult,
    SecuritySettingsResult,
    SettingsResetResult,
    UpdateElfieSettingsCommand,
    UpdateRuntimeSettingsCommand,
    UpdateSecuritySettingsCommand,
)
from .port_models import (
    SpeciesId,
    StoredElfieSettings,
    StoredLoginRateLimit,
    StoredRuntimeSettings,
    StoredSecuritySettings,
)
from .ports import SecuritySettingsChangedPort, SettingsStorePort

MAX_ELFIES_PER_MACHINE: Final = 32
ALLOWED_SPECIES_IDS: Final[frozenset[SpeciesId]] = frozenset({"dog", "fox"})


class SettingsService:
    def __init__(
        self,
        store: SettingsStorePort,
        security_settings_changed: SecuritySettingsChangedPort | None = None,
    ) -> None:
        self._store = store
        self._security_settings_changed = security_settings_changed

    def get_elfie_settings(
        self,
        principal: AccountPrincipal,
        query: GetElfieSettingsQuery,
    ) -> ElfieSettingsResult:
        _ = query
        self._require_manager(principal)
        return self._elfie_result(self._store.load_elfie_settings())

    def update_elfie_settings(
        self,
        principal: AccountPrincipal,
        command: UpdateElfieSettingsCommand,
    ) -> ElfieSettingsResult:
        self._require_manager(principal)
        current = self._store.load_elfie_settings()
        updated = StoredElfieSettings(
            max_elfies_per_user=(
                current.max_elfies_per_user
                if command.max_elfies_per_user is None
                else command.max_elfies_per_user
            ),
            allowed_species_ids=(
                current.allowed_species_ids
                if command.allowed_species_ids is None
                else command.allowed_species_ids
            ),
            personality_presets_enabled=(
                current.personality_presets_enabled
                if command.personality_presets_enabled is None
                else command.personality_presets_enabled
            ),
        )
        self._validate_elfie_settings(updated)
        self._store.save_elfie_settings(updated)
        return self._elfie_result(updated)

    def get_runtime_settings(
        self,
        principal: AccountPrincipal,
        query: GetRuntimeSettingsQuery,
    ) -> RuntimeSettingsResult:
        _ = query
        self._require_manager(principal)
        current = self._store.load_runtime_settings()
        return RuntimeSettingsResult(tick_interval_sec=current.tick_interval_sec)

    def update_runtime_settings(
        self,
        principal: AccountPrincipal,
        command: UpdateRuntimeSettingsCommand,
    ) -> RuntimeSettingsResult:
        self._require_manager(principal)
        current = self._store.load_runtime_settings()
        updated = StoredRuntimeSettings(
            tick_interval_sec=(
                current.tick_interval_sec
                if command.tick_interval_sec is None
                else command.tick_interval_sec
            )
        )
        if updated.tick_interval_sec <= 0:
            raise SettingsValidationError("tick_interval_sec", "必须大于 0")
        self._store.save_runtime_settings(updated)
        return RuntimeSettingsResult(tick_interval_sec=updated.tick_interval_sec)

    def get_security_settings(
        self,
        principal: AccountPrincipal,
        query: GetSecuritySettingsQuery,
    ) -> SecuritySettingsResult:
        _ = query
        self._require_manager(principal)
        return self._security_result(self._store.load_security_settings())

    def update_security_settings(
        self,
        principal: AccountPrincipal,
        command: UpdateSecuritySettingsCommand,
    ) -> SecuritySettingsResult:
        self._require_manager(principal)
        current = self._store.load_security_settings()
        rate_limit = current.rate_limit
        if command.rate_limit is not None:
            rate_limit = StoredLoginRateLimit(
                max_attempts=command.rate_limit.max_attempts,
                window_seconds=command.rate_limit.window_seconds,
            )
        updated = StoredSecuritySettings(
            session_ttl_days=(
                current.session_ttl_days
                if command.session_ttl_days is None
                else command.session_ttl_days
            ),
            rate_limit=rate_limit,
        )
        self._validate_security_settings(updated)
        self._store.save_security_settings(updated)
        if self._security_settings_changed is not None:
            self._security_settings_changed.invalidate_security_cache()
        return self._security_result(updated)

    def reset_settings(
        self,
        principal: AccountPrincipal,
        command: ResetSettingsCommand,
    ) -> SettingsResetResult:
        _ = command
        self._require_manager(principal)
        self._store.reset_settings()
        return SettingsResetResult(
            elfies=self._elfie_result(self._store.load_elfie_settings()),
            runtime=RuntimeSettingsResult(
                tick_interval_sec=self._store.load_runtime_settings().tick_interval_sec
            ),
            security=self._security_result(self._store.load_security_settings()),
        )

    @staticmethod
    def _require_manager(principal: AccountPrincipal) -> None:
        if principal.role not in {"owner", "admin"}:
            raise SettingsForbidden

    @staticmethod
    def _validate_elfie_settings(settings: StoredElfieSettings) -> None:
        if not 1 <= settings.max_elfies_per_user <= MAX_ELFIES_PER_MACHINE:
            raise SettingsValidationError(
                "max_elfies_per_user",
                f"必须在 1 到 {MAX_ELFIES_PER_MACHINE} 之间",
            )
        if not settings.allowed_species_ids:
            raise SettingsValidationError("allowed_species_ids", "至少需要保留一个物种")
        unknown = set(settings.allowed_species_ids) - ALLOWED_SPECIES_IDS
        if unknown:
            raise SettingsValidationError(
                "allowed_species_ids",
                f"不支持的物种: {', '.join(sorted(unknown))}",
            )

    @staticmethod
    def _validate_security_settings(settings: StoredSecuritySettings) -> None:
        if settings.session_ttl_days < 1:
            raise SettingsValidationError("session_ttl_days", "必须至少为 1")
        if settings.rate_limit.max_attempts < 1:
            raise SettingsValidationError("rate_limit.max_attempts", "必须至少为 1")
        if settings.rate_limit.window_seconds < 1:
            raise SettingsValidationError("rate_limit.window_seconds", "必须至少为 1")

    @staticmethod
    def _elfie_result(settings: StoredElfieSettings) -> ElfieSettingsResult:
        return ElfieSettingsResult(
            max_elfies_per_user=settings.max_elfies_per_user,
            allowed_species_ids=settings.allowed_species_ids,
            personality_presets_enabled=settings.personality_presets_enabled,
        )

    @staticmethod
    def _security_result(settings: StoredSecuritySettings) -> SecuritySettingsResult:
        return SecuritySettingsResult(
            session_ttl_days=settings.session_ttl_days,
            rate_limit=LoginRateLimit(
                max_attempts=settings.rate_limit.max_attempts,
                window_seconds=settings.rate_limit.window_seconds,
            ),
        )


__all__ = ("SettingsService",)
