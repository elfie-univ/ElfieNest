"""Public facade for global product Settings."""

from .errors import (
    SettingsError,
    SettingsForbidden,
    SettingsStorageError,
    SettingsValidationError,
)
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
from .service import SettingsService

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
    "SettingsError",
    "SettingsForbidden",
    "SettingsService",
    "SettingsStorageError",
    "SettingsStorePort",
    "SecuritySettingsChangedPort",
    "SettingsValidationError",
    "SpeciesId",
    "StoredElfieSettings",
    "StoredLoginRateLimit",
    "StoredRuntimeSettings",
    "StoredSecuritySettings",
    "UpdateElfieSettingsCommand",
    "UpdateRuntimeSettingsCommand",
    "UpdateSecuritySettingsCommand",
)
