"""Runtime-document Adapter for the Settings Feature Port."""

from __future__ import annotations

import copy
from typing import Any, Mapping, NoReturn, Sequence

from ai_runtime.config import DEFAULT_SYSTEM_SETTINGS
from ai_runtime.storage.config_store import ConfigStoreError
from ai_runtime.storage.runtime_settings import (
    read_runtime_settings,
    write_runtime_settings,
)
from app.features.configuration import (
    SettingsStorageError,
    SpeciesId,
    StoredElfieSettings,
    StoredLoginRateLimit,
    StoredRuntimeSettings,
    StoredSecuritySettings,
)


class RuntimeSettingsAdapter:
    """Preserve unrelated Runtime fields while owning typed ``system`` sections."""

    def load_elfie_settings(self) -> StoredElfieSettings:
        section = self._section("adoption")
        defaults = self._default_section("adoption")
        max_elfies = self._integer(
            section,
            "max_elfies_per_user",
            self._integer(defaults, "max_elfies_per_user", 0),
        )
        species = self._species_sequence(
            section,
            "allowed_species_ids",
            self._species_sequence(defaults, "allowed_species_ids", ()),
        )
        presets = self._boolean_mapping(
            section,
            "personality_presets_enabled",
            self._boolean_mapping(defaults, "personality_presets_enabled", {}),
        )
        return StoredElfieSettings(
            max_elfies_per_user=max_elfies,
            allowed_species_ids=species,
            personality_presets_enabled=tuple(presets.items()),
        )

    def save_elfie_settings(self, settings: StoredElfieSettings) -> None:
        self._save_section(
            "adoption",
            {
                "max_elfies_per_user": settings.max_elfies_per_user,
                "allowed_species_ids": list(settings.allowed_species_ids),
                "personality_presets_enabled": dict(
                    settings.personality_presets_enabled
                ),
            },
        )

    def load_runtime_settings(self) -> StoredRuntimeSettings:
        section = self._section("engine")
        tick_interval = self._number(
            section,
            "tick_interval_sec",
            self._number(
                self._default_section("engine"),
                "tick_interval_sec",
                0.0,
            ),
        )
        return StoredRuntimeSettings(tick_interval_sec=tick_interval)

    def save_runtime_settings(self, settings: StoredRuntimeSettings) -> None:
        self._save_section(
            "engine",
            {"tick_interval_sec": settings.tick_interval_sec},
        )

    def load_security_settings(self) -> StoredSecuritySettings:
        section = self._section("security")
        defaults = self._default_section("security")
        default_rate_limit = defaults.get("rate_limit", {})
        if not isinstance(default_rate_limit, Mapping):
            self._invalid("default system.security.rate_limit", "必须是对象")
        typed_default_rate_limit = self._typed_mapping(default_rate_limit)
        session_ttl_days = self._integer(
            section,
            "session_ttl_days",
            self._integer(defaults, "session_ttl_days", 0),
        )
        raw_rate_limit = section.get("rate_limit", {})
        if not isinstance(raw_rate_limit, Mapping):
            self._invalid("system.security.rate_limit", "必须是对象")
        rate_limit = self._typed_mapping(raw_rate_limit)
        return StoredSecuritySettings(
            session_ttl_days=session_ttl_days,
            rate_limit=StoredLoginRateLimit(
                max_attempts=self._integer(
                    rate_limit,
                    "max_attempts",
                    self._integer(typed_default_rate_limit, "max_attempts", 0),
                ),
                window_seconds=self._integer(
                    rate_limit,
                    "window_seconds",
                    self._integer(typed_default_rate_limit, "window_seconds", 0),
                ),
            ),
        )

    def save_security_settings(self, settings: StoredSecuritySettings) -> None:
        self._save_section(
            "security",
            {
                "session_ttl_days": settings.session_ttl_days,
                "rate_limit": {
                    "max_attempts": settings.rate_limit.max_attempts,
                    "window_seconds": settings.rate_limit.window_seconds,
                },
            },
        )

    def _section(self, name: str) -> dict[str, object]:
        document = self._read_document()
        raw_system = document.get("system", {})
        if not isinstance(raw_system, Mapping):
            self._invalid("system", "必须是对象")
        system = self._typed_mapping(raw_system)
        raw_section = system.get(name, {})
        if not isinstance(raw_section, Mapping):
            self._invalid(f"system.{name}", "必须是对象")
        return self._typed_mapping(raw_section)

    @staticmethod
    def _default_section(name: str) -> dict[str, object]:
        raw_section = DEFAULT_SYSTEM_SETTINGS.get(name)
        if not isinstance(raw_section, Mapping):
            RuntimeSettingsAdapter._invalid(
                f"default system.{name}", "必须是对象"
            )
        return RuntimeSettingsAdapter._typed_mapping(raw_section)

    def _save_section(self, name: str, section: Mapping[str, object]) -> None:
        document = self._read_document()
        raw_system = document.get("system", {})
        if not isinstance(raw_system, Mapping):
            self._invalid("system", "必须是对象")
        system = copy.deepcopy(dict(raw_system))
        system[name] = copy.deepcopy(dict(section))
        document["system"] = system
        try:
            write_runtime_settings(document)
        except ConfigStoreError as error:
            raise SettingsStorageError(str(error)) from error

    @staticmethod
    def _read_document() -> dict[str, Any]:
        try:
            return read_runtime_settings()
        except ConfigStoreError as error:
            raise SettingsStorageError(str(error)) from error

    @classmethod
    def _integer(
        cls,
        section: Mapping[str, object],
        field: str,
        default: int,
    ) -> int:
        value = section.get(field, default)
        if isinstance(value, bool) or not isinstance(value, int):
            cls._invalid(field, "必须是整数")
        return value

    @classmethod
    def _number(
        cls,
        section: Mapping[str, object],
        field: str,
        default: float,
    ) -> float:
        value = section.get(field, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            cls._invalid(field, "必须是数字")
        return float(value)

    @classmethod
    def _species_sequence(
        cls,
        section: Mapping[str, object],
        field: str,
        default: Sequence[SpeciesId],
    ) -> tuple[SpeciesId, ...]:
        value = section.get(field, default)
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            cls._invalid(field, "必须是字符串数组")
        result: list[SpeciesId] = []
        for item in value:
            if item == "dog":
                result.append("dog")
            elif item == "fox":
                result.append("fox")
            else:
                cls._invalid(field, "只支持 dog 或 fox")
        return tuple(result)

    @classmethod
    def _boolean_mapping(
        cls,
        section: Mapping[str, object],
        field: str,
        default: Mapping[str, bool],
    ) -> dict[str, bool]:
        value = section.get(field, default)
        if not isinstance(value, Mapping):
            cls._invalid(field, "必须是布尔值对象")
        result: dict[str, bool] = {}
        for key, enabled in value.items():
            if not isinstance(key, str) or not isinstance(enabled, bool):
                cls._invalid(field, "必须是布尔值对象")
            result[key] = enabled
        return result

    @staticmethod
    def _typed_mapping(value: Mapping[Any, object]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                RuntimeSettingsAdapter._invalid("配置键", "必须是字符串")
            result[key] = item
        return result

    @staticmethod
    def _invalid(field: str, detail: str) -> NoReturn:
        raise SettingsStorageError(f"无效 Runtime 设置 {field}: {detail}")


__all__ = ("RuntimeSettingsAdapter",)
