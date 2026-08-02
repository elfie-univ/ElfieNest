from __future__ import annotations

from dataclasses import replace

import pytest

from ai_runtime.storage.provider_connection_mutations import (
    delete_connection_with_secret,
    finalize_created_connection,
    replace_connection_with_secret,
)
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.secrets import read_secrets, set_connection_secret


def test_failed_create_finalization_removes_connection_and_secret(
    tmp_path, monkeypatch
):
    provider_path = tmp_path / "providers.yaml"
    secret_path = tmp_path / "auth.env"
    store = ProviderConnectionStore(provider_path)
    connection = store.create(catalog_id="openai_api", alias="OpenAI")

    def fail_replace(_connection):
        raise OSError("provider write failed")

    monkeypatch.setattr(store, "replace", fail_replace)

    with pytest.raises(OSError, match="provider write failed"):
        finalize_created_connection(
            store,
            connection,
            "new-secret",
            secret_path=secret_path,
        )

    assert store.load().connections == {}
    assert read_secrets(secret_path) == {}


def test_failed_secret_update_restores_connection_and_previous_secret(tmp_path):
    provider_path = tmp_path / "providers.yaml"
    secret_path = tmp_path / "auth.env"
    store = ProviderConnectionStore(provider_path)
    connection = store.create(catalog_id="openai_api", alias="Original")
    secret_ref = set_connection_secret(
        connection.connection_id,
        "old-secret",
        secret_path,
    )
    connection = replace(connection, credential_ref=secret_ref)
    store.replace(connection)
    updated = replace(connection, alias="Updated")

    def partial_secret_write(connection_id, value, path=None):
        result = set_connection_secret(connection_id, value, path)
        if value == "new-secret":
            raise OSError("secret write failed")
        return result

    with pytest.raises(OSError, match="secret write failed"):
        replace_connection_with_secret(
            store,
            updated,
            "new-secret",
            secret_path=secret_path,
            secret_writer=partial_secret_write,
        )

    assert store.load().connections[connection.connection_id].alias == "Original"
    assert read_secrets(secret_path)[secret_ref] == "old-secret"


def test_failed_secret_delete_restores_connection_and_previous_secret(tmp_path):
    provider_path = tmp_path / "providers.yaml"
    secret_path = tmp_path / "auth.env"
    store = ProviderConnectionStore(provider_path)
    connection = store.create(catalog_id="openai_api", alias="OpenAI")
    secret_ref = set_connection_secret(
        connection.connection_id,
        "old-secret",
        secret_path,
    )

    def partial_secret_clear(connection_id, value, path=None):
        result = set_connection_secret(connection_id, value, path)
        if not value:
            raise OSError("secret clear failed")
        return result

    with pytest.raises(OSError, match="secret clear failed"):
        delete_connection_with_secret(
            store,
            connection.connection_id,
            secret_path=secret_path,
            secret_writer=partial_secret_clear,
        )

    assert connection.connection_id in store.load().connections
    assert read_secrets(secret_path)[secret_ref] == "old-secret"
