"""Closed registry and sources for application configuration documents.

This module owns only technical document selection, resource-root resolution,
YAML decoding and atomic user-document writes.  Semantic validation remains in
the owning App, Elfie, Nest and Infrastructure Models types.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from infrastructure.persistence.configuration.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)


class ConfigDocumentError(RuntimeError):
    """A registered configuration document cannot be loaded or written."""


class ConfigPolicy(str, Enum):
    """Effective-value policy declared by one configuration document."""

    FIELD_OVERLAY = "field_overlay"
    COMPLETE_REPLACEMENT = "complete_replacement"
    BUNDLED_ONLY = "bundled_only"
    USER_ONLY = "user_only"


class ConfigDocumentId(str, Enum):
    """The closed set of application configuration documents."""

    SYSTEM_DEFAULTS = "system_defaults"
    PROVIDER_CATALOG = "provider_catalog"
    MODEL_CATALOG = "model_catalog"
    TOOL_DEFAULTS = "tool_defaults"
    ENERGY_DEFAULTS = "energy_defaults"
    SELFHOOD_DEFAULTS = "selfhood_defaults"
    EMOTION_EXPRESSIONS = "emotion_expressions"
    NEST_DEFAULTS = "nest_defaults"
    RUNTIME_SETTINGS = "runtime_settings"
    PROVIDER_CONNECTIONS = "provider_connections"
    TOOL_SETTINGS = "tool_settings"
    PROVIDER_CATALOG_OVERRIDE = "provider_catalog_override"
    AUTH_ENV = "auth_env"


@dataclass(frozen=True)
class ConfigDocumentSpec:
    """Static metadata for one approved document."""

    document_id: ConfigDocumentId
    bundled_relative_path: str | None
    user_relative_path: str | None
    version: int
    policy: ConfigPolicy
    owner: str
    required_bundled: bool = False


@dataclass(frozen=True)
class LoadedConfigDocument:
    """A decoded registered document with its resolved path."""

    spec: ConfigDocumentSpec
    path: Path
    document: Mapping[str, Any]


CONFIG_DOCUMENTS: Mapping[ConfigDocumentId, ConfigDocumentSpec] = {
    ConfigDocumentId.SYSTEM_DEFAULTS: ConfigDocumentSpec(
        ConfigDocumentId.SYSTEM_DEFAULTS,
        "app/system-defaults.yaml",
        "runtime.yaml",
        1,
        ConfigPolicy.FIELD_OVERLAY,
        "app.configuration.settings",
        True,
    ),
    ConfigDocumentId.PROVIDER_CATALOG: ConfigDocumentSpec(
        ConfigDocumentId.PROVIDER_CATALOG,
        "models/provider-catalog.yaml",
        None,
        2,
        ConfigPolicy.BUNDLED_ONLY,
        "infrastructure.models",
        True,
    ),
    ConfigDocumentId.MODEL_CATALOG: ConfigDocumentSpec(
        ConfigDocumentId.MODEL_CATALOG,
        "models/model-catalog.yaml",
        None,
        1,
        ConfigPolicy.BUNDLED_ONLY,
        "infrastructure.models",
        True,
    ),
    ConfigDocumentId.TOOL_DEFAULTS: ConfigDocumentSpec(
        ConfigDocumentId.TOOL_DEFAULTS,
        "tools/defaults.yaml",
        None,
        1,
        ConfigPolicy.BUNDLED_ONLY,
        "app.configuration.capabilities",
        True,
    ),
    ConfigDocumentId.ENERGY_DEFAULTS: ConfigDocumentSpec(
        ConfigDocumentId.ENERGY_DEFAULTS,
        "brain/energy.yaml",
        None,
        1,
        ConfigPolicy.BUNDLED_ONLY,
        "elfie.brain.energy",
        True,
    ),
    ConfigDocumentId.SELFHOOD_DEFAULTS: ConfigDocumentSpec(
        ConfigDocumentId.SELFHOOD_DEFAULTS,
        "brain/selfhood.yaml",
        None,
        1,
        ConfigPolicy.BUNDLED_ONLY,
        "elfie.brain.selfhood",
        True,
    ),
    ConfigDocumentId.EMOTION_EXPRESSIONS: ConfigDocumentSpec(
        ConfigDocumentId.EMOTION_EXPRESSIONS,
        "brain/emotion-expressions.yaml",
        None,
        1,
        ConfigPolicy.BUNDLED_ONLY,
        "elfie.brain.emotion",
        True,
    ),
    ConfigDocumentId.NEST_DEFAULTS: ConfigDocumentSpec(
        ConfigDocumentId.NEST_DEFAULTS,
        "nest/defaults.yaml",
        None,
        1,
        ConfigPolicy.BUNDLED_ONLY,
        "nest",
        True,
    ),
    ConfigDocumentId.RUNTIME_SETTINGS: ConfigDocumentSpec(
        ConfigDocumentId.RUNTIME_SETTINGS,
        None,
        "runtime.yaml",
        1,
        ConfigPolicy.FIELD_OVERLAY,
        "app.configuration.settings",
    ),
    ConfigDocumentId.PROVIDER_CONNECTIONS: ConfigDocumentSpec(
        ConfigDocumentId.PROVIDER_CONNECTIONS,
        None,
        "providers.yaml",
        2,
        ConfigPolicy.USER_ONLY,
        "app.configuration.providers",
    ),
    ConfigDocumentId.TOOL_SETTINGS: ConfigDocumentSpec(
        ConfigDocumentId.TOOL_SETTINGS,
        None,
        "tools.yaml",
        1,
        ConfigPolicy.FIELD_OVERLAY,
        "app.configuration.capabilities",
    ),
    ConfigDocumentId.PROVIDER_CATALOG_OVERRIDE: ConfigDocumentSpec(
        ConfigDocumentId.PROVIDER_CATALOG_OVERRIDE,
        None,
        "provider-catalog.yaml",
        2,
        ConfigPolicy.COMPLETE_REPLACEMENT,
        "infrastructure.models",
    ),
    ConfigDocumentId.AUTH_ENV: ConfigDocumentSpec(
        ConfigDocumentId.AUTH_ENV,
        None,
        "auth.env",
        1,
        ConfigPolicy.USER_ONLY,
        "secret-capability",
    ),
}


def document_spec(document_id: ConfigDocumentId) -> ConfigDocumentSpec:
    """Return metadata for one known document ID."""

    try:
        return CONFIG_DOCUMENTS[document_id]
    except KeyError as exc:  # pragma: no cover - Enum typing makes this defensive.
        raise ConfigDocumentError(f"未注册的配置文档: {document_id!r}") from exc


def resolve_bundled_config_root(
    explicit_root: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    runtime_mode: str | None = None,
) -> Path:
    """Resolve the one bundled root for development or installed execution.

    Development uses the repository root explicitly.  Installed execution
    must receive the staged resource root from its launcher and never searches
    the current working directory or a source checkout.
    """

    if explicit_root is not None:
        return explicit_root.expanduser().resolve()
    env = os.environ if environment is None else environment
    configured = env.get("ELFIENEST_BUNDLED_CONFIG_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    mode = (
        runtime_mode
        if runtime_mode is not None
        else env.get("ELFIENEST_RUNTIME_MODE", "dev")
    )
    if mode == "release":
        raise ConfigDocumentError(
            "安装态必须由 launcher 提供 ELFIENEST_BUNDLED_CONFIG_DIR"
        )
    return Path(__file__).resolve().parents[3] / "config"


class BundledConfigSource:
    """Read only registered bundled documents from one explicit root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = resolve_bundled_config_root(root)

    def load(self, document_id: ConfigDocumentId) -> LoadedConfigDocument:
        spec = document_spec(document_id)
        if spec.bundled_relative_path is None:
            raise ConfigDocumentError(f"文档没有 bundled 来源: {document_id.value}")
        path = _safe_join(self.root, spec.bundled_relative_path)
        if not path.is_file():
            if spec.required_bundled:
                raise ConfigDocumentError(
                    f"必需 bundled 配置缺失 document={document_id.value} path={path}"
                )
            return LoadedConfigDocument(spec, path, {})
        try:
            document = read_yaml_mapping(path)
        except ConfigStoreError as exc:
            raise ConfigDocumentError(
                f"bundled 配置不可读 document={document_id.value} path={path}"
            ) from exc
        _validate_version(spec, document, path)
        return LoadedConfigDocument(spec, path, document)


class RuntimeConfigSource:
    """Read/write only registered user configuration documents."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def load(self, document_id: ConfigDocumentId) -> LoadedConfigDocument | None:
        spec = document_spec(document_id)
        if spec.user_relative_path is None:
            raise ConfigDocumentError(f"文档没有 user 来源: {document_id.value}")
        path = _safe_join(self.root, spec.user_relative_path)
        if not path.is_file():
            return None
        try:
            document = read_yaml_mapping(path)
        except ConfigStoreError as exc:
            raise ConfigDocumentError(
                f"用户配置不可读 document={document_id.value} path={path}"
            ) from exc
        _validate_version(spec, document, path)
        return LoadedConfigDocument(spec, path, document)

    def write(
        self,
        document_id: ConfigDocumentId,
        document: Mapping[str, Any],
    ) -> Path:
        spec = document_spec(document_id)
        if spec.user_relative_path is None:
            raise ConfigDocumentError(f"文档没有 user 来源: {document_id.value}")
        path = _safe_join(self.root, spec.user_relative_path)
        payload = dict(document)
        existing_version = payload.get("version")
        if existing_version is not None and existing_version != spec.version:
            raise ConfigDocumentError(
                f"用户配置版本不匹配 document={document_id.value} version={existing_version!r}"
            )
        payload["version"] = spec.version
        try:
            write_yaml_mapping(path, payload)
        except ConfigStoreError as exc:
            raise ConfigDocumentError(
                f"用户配置不可写 document={document_id.value} path={path}"
            ) from exc
        return path


def _safe_join(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ConfigDocumentError(f"配置路径越界: {relative}") from exc
    return candidate


def _validate_version(
    spec: ConfigDocumentSpec,
    document: Mapping[str, Any],
    path: Path,
) -> None:
    if document.get("version") != spec.version:
        raise ConfigDocumentError(
            f"配置文档版本不支持 document={spec.document_id.value} "
            f"version={document.get('version')!r} expected={spec.version} path={path}"
        )


__all__ = (
    "CONFIG_DOCUMENTS",
    "BundledConfigSource",
    "ConfigDocumentError",
    "ConfigDocumentId",
    "ConfigDocumentSpec",
    "ConfigPolicy",
    "LoadedConfigDocument",
    "RuntimeConfigSource",
    "document_spec",
    "resolve_bundled_config_root",
)
