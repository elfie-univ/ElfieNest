"""Outbound Ports consumed by the Settings Feature."""

from __future__ import annotations

from typing import Protocol

from .port_models import (
    StoredElfieSettings,
    StoredRuntimeSettings,
    StoredSecuritySettings,
)


class SettingsStorePort(Protocol):
    """Read and atomically update each owned Runtime settings section."""

    def load_elfie_settings(self) -> StoredElfieSettings:
        ...

    def save_elfie_settings(self, settings: StoredElfieSettings) -> None:
        ...

    def load_runtime_settings(self) -> StoredRuntimeSettings:
        ...

    def save_runtime_settings(self, settings: StoredRuntimeSettings) -> None:
        ...

    def load_security_settings(self) -> StoredSecuritySettings:
        ...

    def save_security_settings(self, settings: StoredSecuritySettings) -> None:
        ...

    def reset_settings(self) -> None:
        ...


__all__ = ("SettingsStorePort",)
