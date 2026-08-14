"""Settings-backed policy Adapter for Adoption."""

from __future__ import annotations

from app.features.adoption import AdoptionPolicyRecord, AdoptionPortError
from app.features.configuration.settings import SettingsError, SettingsStorePort
from elfie.profile import PERSONALITY_PRESETS


class SettingsAdoptionPolicyAdapter:
    def __init__(self, settings: SettingsStorePort) -> None:
        self._settings = settings

    def load_policy(self) -> AdoptionPolicyRecord:
        try:
            settings = self._settings.load_elfie_settings()
        except SettingsError as error:
            raise AdoptionPortError("unable to read Adoption policy") from error
        enabled_map = dict(settings.personality_presets_enabled)
        enabled = tuple(
            name for name in PERSONALITY_PRESETS if enabled_map.get(name, True)
        )
        if not enabled:
            enabled = tuple(PERSONALITY_PRESETS)
        return AdoptionPolicyRecord(
            default_elfie_limit=settings.max_elfies_per_user,
            enabled_personality_styles=enabled,
        )


__all__ = ("SettingsAdoptionPolicyAdapter",)
