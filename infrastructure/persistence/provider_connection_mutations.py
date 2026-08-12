"""Compensating mutations across Provider config and connection secrets."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

from infrastructure.models.provider_records import ProviderConnection
from infrastructure.persistence.configuration.secrets import (
    connection_secret_name,
    read_secrets,
    set_connection_secret,
)
from infrastructure.persistence.provider_connections import ProviderConnectionStore

SecretWriter = Callable[[str, str, Optional[Path]], str]


def finalize_created_connection(
    store: ProviderConnectionStore,
    connection: ProviderConnection,
    api_key: Optional[str],
    *,
    secret_path: Optional[Path] = None,
    secret_writer: SecretWriter = set_connection_secret,
) -> ProviderConnection:
    """Attach a secret to a newly persisted connection or roll the create back."""
    if api_key is None:
        return connection
    credential_ref = connection_secret_name(connection.connection_id)
    finalized = replace(connection, credential_ref=credential_ref)
    try:
        store.replace(finalized)
        secret_writer(connection.connection_id, api_key, secret_path)
    except Exception:
        store.delete(connection.connection_id)
        _restore_secret(
            connection.connection_id,
            "",
            secret_path,
            secret_writer,
        )
        raise
    return finalized


def replace_connection_with_secret(
    store: ProviderConnectionStore,
    connection: ProviderConnection,
    api_key: Optional[str],
    *,
    secret_path: Optional[Path] = None,
    secret_writer: SecretWriter = set_connection_secret,
) -> ProviderConnection:
    """Replace a connection and compensate if its secret update fails."""
    previous = store.load().connections.get(connection.connection_id)
    if previous is None:
        raise ValueError(f"Provider connection not found: {connection.connection_id}")
    if api_key is None:
        store.replace(connection)
        return connection

    secret_name = connection_secret_name(connection.connection_id)
    previous_secret = read_secrets(secret_path).get(secret_name, "")
    updated = replace(connection, credential_ref=secret_name)
    store.replace(updated)
    try:
        secret_writer(connection.connection_id, api_key, secret_path)
    except Exception:
        store.replace(previous)
        _restore_secret(
            connection.connection_id,
            previous_secret,
            secret_path,
            secret_writer,
        )
        raise
    return updated


def delete_connection_with_secret(
    store: ProviderConnectionStore,
    connection_id: str,
    *,
    secret_path: Optional[Path] = None,
    secret_writer: SecretWriter = set_connection_secret,
) -> bool:
    """Delete a connection and restore it if clearing its secret fails."""
    connection = store.load().connections.get(connection_id)
    if connection is None:
        return False
    secret_name = connection_secret_name(connection_id)
    previous_secret = read_secrets(secret_path).get(secret_name, "")
    if not store.delete(connection_id):
        return False
    try:
        secret_writer(connection_id, "", secret_path)
    except Exception:
        store.replace(connection)
        if previous_secret:
            _restore_secret(
                connection_id,
                previous_secret,
                secret_path,
                secret_writer,
            )
        raise
    return True


def _restore_secret(
    connection_id: str,
    value: str,
    secret_path: Optional[Path],
    secret_writer: SecretWriter,
) -> None:
    try:
        secret_writer(connection_id, value, secret_path)
    except Exception:
        pass


__all__ = [
    "delete_connection_with_secret",
    "finalize_created_connection",
    "replace_connection_with_secret",
]
