from __future__ import annotations

from dataclasses import replace

import pytest

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.configuration.settings import (
    GetElfieSettingsQuery,
    LoginRateLimit,
    SettingsForbidden,
    SettingsService,
    SettingsValidationError,
    StoredElfieSettings,
    StoredLoginRateLimit,
    StoredRuntimeSettings,
    StoredSecuritySettings,
    UpdateElfieSettingsCommand,
    UpdateRuntimeSettingsCommand,
    UpdateSecuritySettingsCommand,
)


class MemorySettingsStore:
    def __init__(self) -> None:
        self.elfies = StoredElfieSettings(
            max_elfies_per_user=3,
            allowed_species_ids=("dog", "fox"),
            personality_presets_enabled=(("安静温顺", True),),
        )
        self.runtime = StoredRuntimeSettings(tick_interval_sec=1.5)
        self.security = StoredSecuritySettings(
            session_ttl_days=7,
            rate_limit=StoredLoginRateLimit(max_attempts=5, window_seconds=300),
        )

    def load_elfie_settings(self) -> StoredElfieSettings:
        return self.elfies

    def save_elfie_settings(self, settings: StoredElfieSettings) -> None:
        self.elfies = settings

    def load_runtime_settings(self) -> StoredRuntimeSettings:
        return self.runtime

    def save_runtime_settings(self, settings: StoredRuntimeSettings) -> None:
        self.runtime = settings

    def load_security_settings(self) -> StoredSecuritySettings:
        return self.security

    def save_security_settings(self, settings: StoredSecuritySettings) -> None:
        self.security = settings


def principal(role: AccountRole = "owner") -> AccountPrincipal:
    return AccountPrincipal(
        user_id=1,
        account_id="owner",
        role=role,
        default_landing_page="manage",
    )


def test_partial_elfie_update_preserves_other_settings() -> None:
    store = MemorySettingsStore()
    service = SettingsService(store)

    result = service.update_elfie_settings(
        principal(),
        UpdateElfieSettingsCommand(max_elfies_per_user=4),
    )

    assert result.max_elfies_per_user == 4
    assert result.allowed_species_ids == ("dog", "fox")
    assert dict(result.personality_presets_enabled)["安静温顺"] is True


@pytest.mark.parametrize(
    "command",
    [
        UpdateElfieSettingsCommand(max_elfies_per_user=0),
        UpdateElfieSettingsCommand(max_elfies_per_user=33),
        UpdateElfieSettingsCommand(allowed_species_ids=()),
        UpdateElfieSettingsCommand(allowed_species_ids=("cat",)),
    ],
)
def test_invalid_elfie_settings_are_rejected(
    command: UpdateElfieSettingsCommand,
) -> None:
    with pytest.raises(SettingsValidationError):
        SettingsService(MemorySettingsStore()).update_elfie_settings(
            principal(), command
        )


def test_runtime_and_security_constraints_are_owned_by_feature() -> None:
    service = SettingsService(MemorySettingsStore())

    with pytest.raises(SettingsValidationError):
        service.update_runtime_settings(
            principal(), UpdateRuntimeSettingsCommand(tick_interval_sec=0)
        )
    with pytest.raises(SettingsValidationError):
        service.update_security_settings(
            principal(),
            UpdateSecuritySettingsCommand(
                rate_limit=LoginRateLimit(max_attempts=0, window_seconds=60)
            ),
        )


def test_non_manager_cannot_read_or_write_settings() -> None:
    service = SettingsService(MemorySettingsStore())
    user = principal("user")

    with pytest.raises(SettingsForbidden):
        service.get_elfie_settings(user, GetElfieSettingsQuery())
    with pytest.raises(SettingsForbidden):
        service.update_elfie_settings(
            user, UpdateElfieSettingsCommand(max_elfies_per_user=2)
        )


def test_security_update_preserves_unspecified_rate_limit() -> None:
    store = MemorySettingsStore()
    store.security = replace(store.security, session_ttl_days=9)

    result = SettingsService(store).update_security_settings(
        principal(), UpdateSecuritySettingsCommand(session_ttl_days=2)
    )

    assert result.session_ttl_days == 2
    assert result.rate_limit.max_attempts == 5
    assert result.rate_limit.window_seconds == 300
