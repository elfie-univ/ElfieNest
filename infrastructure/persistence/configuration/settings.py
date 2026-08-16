"""Runtime-document Adapter for the Settings Feature Port."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Mapping, NoReturn

from app.features.configuration import (
    SettingsStorageError,
    StoredElfieSettings,
    StoredLoginRateLimit,
    StoredRuntimeSettings,
    StoredSecuritySettings,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_system_defaults,
)
from infrastructure.persistence.configuration.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)
from infrastructure.persistence.configuration.documents import ConfigDocumentId
from infrastructure.persistence.configuration.runtime_settings import (
    CONFIG_DOCUMENT_VERSION,
    read_runtime_settings,
    write_runtime_settings,
)
from infrastructure.persistence.configuration.schemas import (
    ConfigSchemaError,
    validate_registered_document,
)
from infrastructure.persistence.layout.data_home import get_config_path


class RuntimeSettingsAdapter:
    """Preserve unrelated Runtime fields while owning typed ``system`` sections."""

    def __init__(
        self,
        config_path: Path | None = None,
        *,
        bundled_root: Path | None = None,
    ) -> None:
        self._config_path = config_path or get_config_path()
        self._bundled_root = bundled_root

    def load_elfie_settings(self) -> StoredElfieSettings:
        section = self._section("adoption")
        defaults = self._default_section("adoption")
        max_elfies = self._integer(
            section,
            "max_elfies_per_user",
            self._integer(defaults, "max_elfies_per_user", 0),
        )
        presets = self._boolean_mapping(
            section,
            "personality_presets_enabled",
            self._boolean_mapping(defaults, "personality_presets_enabled", {}),
        )
        return StoredElfieSettings(
            max_elfies_per_user=max_elfies,
            personality_presets_enabled=tuple(presets.items()),
        )

    def save_elfie_settings(self, settings: StoredElfieSettings) -> None:
        self._save_section(
            "adoption",
            {
                "max_elfies_per_user": settings.max_elfies_per_user,
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

    def reset_settings(self) -> None:
        document = self._read_document()
        document.pop("system", None)
        self._write_document(document)

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

    def _default_section(self, name: str) -> dict[str, object]:
        raw_section = load_system_defaults(root=self._bundled_root).get(name)
        if not isinstance(raw_section, Mapping):
            self._invalid(f"default system.{name}", "必须是对象")
        return self._typed_mapping(raw_section)

    def _save_section(self, name: str, section: Mapping[str, object]) -> None:
        document = self._read_document()
        raw_system = document.get("system", {})
        if not isinstance(raw_system, Mapping):
            self._invalid("system", "必须是对象")
        system = copy.deepcopy(dict(raw_system))
        system[name] = copy.deepcopy(dict(section))
        document["system"] = system
        self._write_document(document)

    def _read_document(self) -> dict[str, Any]:
        try:
            if self._config_path == get_config_path():
                return read_runtime_settings()
            document = copy.deepcopy(read_yaml_mapping(self._config_path))
            self._validate_document(document)
            document.pop("version", None)
            return document
        except ConfigStoreError as error:
            raise SettingsStorageError(str(error)) from error

    def _write_document(self, document: Mapping[str, Any]) -> None:
        try:
            if self._config_path == get_config_path():
                write_runtime_settings(document)
                return
            payload = {
                "version": CONFIG_DOCUMENT_VERSION,
                **copy.deepcopy(dict(document)),
            }
            self._validate_document(payload)
            if self._config_path.exists():
                shutil.copy2(
                    str(self._config_path),
                    str(
                        self._config_path.with_suffix(f"{self._config_path.suffix}.bak")
                    ),
                )
            write_yaml_mapping(
                self._config_path,
                payload,
            )
        except (ConfigStoreError, OSError) as error:
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

    def _validate_document(self, document: Mapping[str, Any]) -> None:
        if not document:
            return
        if document.get("version") != CONFIG_DOCUMENT_VERSION:
            raise SettingsStorageError(
                f"Runtime 设置版本不支持: {document.get('version')!r}"
            )
        try:
            validate_registered_document(
                ConfigDocumentId.RUNTIME_SETTINGS,
                document,
                self._config_path,
            )
        except ConfigSchemaError as error:
            raise SettingsStorageError(str(error)) from error


__all__ = ("RuntimeSettingsAdapter",)
