"""Atomic storage for Provider connection configuration version 2."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Tuple

from ai_runtime.storage.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)
from ai_runtime.storage.data_home import ensure_elfie_home, get_provider_config_path
from ai_runtime.storage.provider_connection_records import (
    CONNECTION_DOCUMENT_VERSION,
    CONNECTION_ID_PATTERN,
    InvalidProviderConnectionDocument,
    ModelSource,
    ProviderConnection,
    ProviderConnectionDocument,
    ProviderModelRecord,
    is_connection_id,
    parse_provider_document,
)


class ProviderConnectionStoreError(ConfigStoreError):
    """Provider connection configuration is malformed."""


class ProviderConnectionStore:
    """Read and write the sole Provider connection source of truth."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or get_provider_config_path()
        self._uses_default_path = path is None

    def load(self) -> ProviderConnectionDocument:
        raw = read_yaml_mapping(self.path)
        if not raw:
            return ProviderConnectionDocument()
        try:
            return parse_provider_document(raw)
        except InvalidProviderConnectionDocument as exc:
            raise ProviderConnectionStoreError(str(exc)) from exc

    def save(self, document: ProviderConnectionDocument) -> None:
        if document.version != CONNECTION_DOCUMENT_VERSION:
            raise ProviderConnectionStoreError("Provider 连接配置只能写入 v2")
        if self._uses_default_path:
            ensure_elfie_home()
        write_yaml_mapping(self.path, document.to_dict())

    def create(
        self,
        *,
        catalog_id: str,
        alias: str,
        api_base: str = "",
        api_mode: str = "",
        auth_type: str = "",
        credential_ref: str = "",
        installation: Optional[Mapping[str, str]] = None,
        models: Tuple[ProviderModelRecord, ...] = (),
    ) -> ProviderConnection:
        document = self.load()
        next_value = document.counters.get(catalog_id, 0) + 1
        connection_id = f"{catalog_id}_{next_value:04d}"
        while connection_id in document.connections:
            next_value += 1
            connection_id = f"{catalog_id}_{next_value:04d}"
        connection = ProviderConnection(
            connection_id=connection_id,
            catalog_id=catalog_id,
            alias=alias,
            api_base=api_base,
            api_mode=api_mode,
            auth_type=auth_type,
            credential_ref=credential_ref,
            installation=dict(installation or {}),
            models=models,
        )
        connections = dict(document.connections)
        connections[connection_id] = connection
        counters = dict(document.counters)
        counters[catalog_id] = next_value
        self.save(
            ProviderConnectionDocument(counters=counters, connections=connections)
        )
        return connection

    def replace(self, connection: ProviderConnection) -> None:
        document = self.load()
        match = CONNECTION_ID_PATTERN.fullmatch(connection.connection_id)
        if match is None:
            raise ProviderConnectionStoreError(
                f"无效 connection_id: {connection.connection_id!r}"
            )
        connections = dict(document.connections)
        connections[connection.connection_id] = connection
        counters = dict(document.counters)
        counters[connection.catalog_id] = max(
            counters.get(connection.catalog_id, 0), int(match.group(2))
        )
        self.save(
            ProviderConnectionDocument(counters=counters, connections=connections)
        )

    def delete(self, connection_id: str) -> bool:
        document = self.load()
        if connection_id not in document.connections:
            return False
        connections = dict(document.connections)
        del connections[connection_id]
        self.save(
            ProviderConnectionDocument(
                counters=dict(document.counters), connections=connections
            )
        )
        return True


__all__ = [
    "CONNECTION_DOCUMENT_VERSION",
    "ModelSource",
    "ProviderConnection",
    "ProviderConnectionDocument",
    "ProviderConnectionStore",
    "ProviderConnectionStoreError",
    "ProviderModelRecord",
    "is_connection_id",
]
