"""Adapter exposing the Settings authority through the Accounts quota Port."""

from __future__ import annotations

from app.features.accounts import AccountQuotaPolicyError
from app.features.configuration.settings import SettingsError, SettingsStorePort


class SettingsAccountQuotaPolicyAdapter:
    def __init__(self, settings: SettingsStorePort) -> None:
        self._settings = settings

    def default_elfie_limit(self) -> int:
        try:
            value = self._settings.load_elfie_settings().max_elfies_per_user
        except SettingsError as error:
            raise AccountQuotaPolicyError(str(error)) from error
        if isinstance(value, bool) or not isinstance(value, int):
            raise AccountQuotaPolicyError("invalid default Elfie limit")
        return int(value)


__all__ = ("SettingsAccountQuotaPolicyAdapter",)
