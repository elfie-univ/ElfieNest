"""Storage boundary for Runtime settings and Tool settings documents."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Mapping

from infrastructure.persistence.configuration.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)
from infrastructure.persistence.configuration.documents import ConfigDocumentId
from infrastructure.persistence.configuration.schemas import (
    ConfigSchemaError,
    validate_registered_document,
)
from infrastructure.persistence.layout.data_home import (
    ensure_elfie_home,
    get_config_path,
    get_tool_config_path,
)

CONFIG_DOCUMENT_VERSION = 1


def _backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(str(path), str(path.with_suffix(f"{path.suffix}.bak")))


def read_runtime_settings() -> dict[str, Any]:
    """Read only the user-owned Runtime settings document."""
    config = copy.deepcopy(read_yaml_mapping(get_config_path()))
    _validate_runtime_document(config, get_config_path())
    config.pop("version", None)
    if "providers" in config:
        raise ConfigStoreError(
            "Runtime 设置不接受 providers；请使用 ProviderConnectionStore"
        )

    return config


def read_tool_settings() -> dict[str, Any]:
    """Read only the user-owned Tool settings document."""
    document = copy.deepcopy(read_yaml_mapping(get_tool_config_path()))
    _validate_runtime_document(
        document, get_tool_config_path(), ConfigDocumentId.TOOL_SETTINGS
    )
    document.pop("version", None)
    return document


def write_runtime_settings(
    config: Mapping[str, Any],
    *,
    backup_existing: bool = True,
) -> None:
    """Write only Runtime settings without touching Tool or Provider data."""
    if "providers" in config:
        raise ConfigStoreError(
            "Runtime 设置不接受 providers；请使用 ProviderConnectionStore"
        )
    runtime_policy = config.get("runtime_policy")
    if isinstance(runtime_policy, Mapping) and "tools" in runtime_policy:
        raise ConfigStoreError(
            "Runtime 设置不接受 runtime_policy.tools；请使用 ToolSettingsAdapter"
        )
    safe_config = copy.deepcopy(dict(config))
    path = get_config_path()
    document = {"version": CONFIG_DOCUMENT_VERSION, **safe_config}
    _validate_runtime_document(document, path)
    ensure_elfie_home()
    if read_yaml_mapping(path) == document:
        return
    if backup_existing:
        _backup(path)
    write_yaml_mapping(path, document)


def write_tool_settings(
    tools: Mapping[str, Any],
    *,
    backup_existing: bool = True,
) -> None:
    """Write the dedicated user Tool settings document."""
    path = get_tool_config_path()
    document = {"version": CONFIG_DOCUMENT_VERSION, "tools": copy.deepcopy(dict(tools))}
    _validate_runtime_document(document, path, ConfigDocumentId.TOOL_SETTINGS)
    ensure_elfie_home()
    if read_yaml_mapping(path) == document:
        return
    if backup_existing:
        _backup(path)
    write_yaml_mapping(path, document)


def _validate_runtime_document(
    document: Mapping[str, Any],
    path: Path,
    document_id: ConfigDocumentId = ConfigDocumentId.RUNTIME_SETTINGS,
) -> None:
    if not document:
        return
    if document.get("version") != CONFIG_DOCUMENT_VERSION:
        raise ConfigStoreError(
            f"{document_id.value} 配置版本不支持: {document.get('version')!r}"
        )
    try:
        validate_registered_document(document_id, document, path)
    except ConfigSchemaError as exc:
        raise ConfigStoreError(str(exc)) from exc
