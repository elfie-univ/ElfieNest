"""Composition adapter joining Provider records, secrets and mutations."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.storage_ports import ProviderStorageError
from infrastructure.persistence.configuration.secrets import resolve_secret
from infrastructure.persistence.provider_connection_mutations import (
    delete_connection_with_secret,
    finalize_created_connection,
    replace_connection_with_secret,
)
from infrastructure.persistence.provider_connections import (
    ProviderConnectionStore,
    ProviderConnectionStoreError,
)


class ProviderStorageAdapter:
    """Implement the Models-owned ProviderStoragePort in Persistence."""

    def __init__(
        self,
        store: ProviderConnectionStore,
        *,
        secret_path: Path | None = None,
    ) -> None:
        self._store = store
        self._secret_path = secret_path

    def load_connections(self) -> Mapping[str, ProviderConnection]:
        try:
            return self._store.load().connections
        except (ProviderConnectionStoreError, OSError, ValueError) as error:
            raise ProviderStorageError("Unable to read Provider connections") from error

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
        models: tuple[ProviderModelRecord, ...] = (),
    ) -> ProviderConnection:
        try:
            return self._store.create(
                catalog_id=catalog_id,
                alias=alias,
                api_base=api_base,
                api_mode=api_mode,
                auth_type=auth_type,
                credential_ref=credential_ref,
                installation=installation,
                models=models,
            )
        except (ProviderConnectionStoreError, OSError, ValueError) as error:
            raise ProviderStorageError(
                "Unable to create Provider connection"
            ) from error

    def replace(self, connection: ProviderConnection) -> None:
        try:
            self._store.replace(connection)
        except (ProviderConnectionStoreError, OSError, ValueError) as error:
            raise ProviderStorageError(
                "Unable to replace Provider connection"
            ) from error

    def delete(self, connection_id: str) -> bool:
        try:
            return self._store.delete(connection_id)
        except (ProviderConnectionStoreError, OSError, ValueError) as error:
            raise ProviderStorageError(
                "Unable to delete Provider connection"
            ) from error

    def create_with_secret(
        self, connection: ProviderConnection, api_key: str | None
    ) -> ProviderConnection:
        try:
            return finalize_created_connection(
                self._store,
                connection,
                api_key,
                secret_path=self._secret_path,
            )
        except (ProviderConnectionStoreError, OSError, ValueError) as error:
            raise ProviderStorageError("Unable to save Provider credential") from error

    def replace_with_secret(
        self,
        connection: ProviderConnection,
        api_key: str | None,
    ) -> ProviderConnection:
        try:
            return replace_connection_with_secret(
                self._store,
                connection,
                api_key,
                secret_path=self._secret_path,
            )
        except (ProviderConnectionStoreError, OSError, ValueError) as error:
            raise ProviderStorageError(
                "Unable to update Provider credential"
            ) from error

    def delete_with_secret(self, connection_id: str) -> bool:
        try:
            return delete_connection_with_secret(
                self._store,
                connection_id,
                secret_path=self._secret_path,
            )
        except (ProviderConnectionStoreError, OSError, ValueError) as error:
            raise ProviderStorageError(
                "Unable to delete Provider credential"
            ) from error

    def has_secret(self, credential_ref: str) -> bool:
        try:
            return bool(resolve_secret(credential_ref, self._secret_path))
        except OSError as error:
            raise ProviderStorageError(
                "Unable to resolve Provider credential"
            ) from error

    def resolve_secret(self, credential_ref: str) -> str:
        try:
            return resolve_secret(credential_ref, self._secret_path)
        except OSError as error:
            raise ProviderStorageError(
                "Unable to resolve Provider credential"
            ) from error


__all__ = ("ProviderStorageAdapter",)
