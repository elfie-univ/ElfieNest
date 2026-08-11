import json
import os
import stat

import pytest

from infrastructure.persistence.configuration.oauth_credentials import (
    InvalidOAuthCredentialIdError,
    OAuthCredential,
    OAuthCredentialStore,
    OAuthCredentialStoreError,
)
from infrastructure.persistence.layout.data_home import get_credentials_dir


def test_oauth_credential_round_trip_redacts_public_projection_and_repr(tmp_path):
    store = OAuthCredentialStore(tmp_path / "oauth")
    credential = OAuthCredential(
        provider_id="openai",
        access_token="access-placeholder",
        refresh_token="refresh-placeholder",
        expires_at="2026-07-29T12:00:00Z",
        scopes=("openid", "profile"),
        account_id="account-placeholder",
    )

    path = store.save(credential)
    loaded = store.load("openai")

    assert loaded == credential
    assert path == tmp_path / "oauth" / "openai.json"
    assert "access-placeholder" not in repr(loaded)
    assert "refresh-placeholder" not in repr(loaded)
    assert loaded.public_view() == {
        "provider_id": "openai",
        "expires_at": "2026-07-29T12:00:00Z",
        "scopes": ["openid", "profile"],
        "account_id": "account-placeholder",
        "token_type": "Bearer",
        "has_access_token": True,
        "has_refresh_token": True,
    }
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_default_oauth_store_secures_credentials_parent(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "elfie-home"))

    path = OAuthCredentialStore().save(
        OAuthCredential(provider_id="openai", access_token="placeholder")
    )

    if os.name != "nt":
        assert stat.S_IMODE(get_credentials_dir().stat().st_mode) == 0o700
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_oauth_credential_save_atomically_replaces_refreshed_tokens(tmp_path):
    store = OAuthCredentialStore(tmp_path / "oauth")
    store.save(OAuthCredential(provider_id="openai", access_token="first"))

    store.save(
        OAuthCredential(
            provider_id="openai",
            access_token="second",
            refresh_token="refresh-second",
        )
    )

    assert store.load("openai") == OAuthCredential(
        provider_id="openai",
        access_token="second",
        refresh_token="refresh-second",
    )
    assert [path.name for path in (tmp_path / "oauth").iterdir()] == ["openai.json"]


def test_oauth_credential_store_rejects_path_traversal_and_malformed_data(tmp_path):
    store = OAuthCredentialStore(tmp_path / "oauth")

    with pytest.raises(InvalidOAuthCredentialIdError):
        store.load("../escape")

    malformed_path = tmp_path / "oauth" / "openai.json"
    malformed_path.parent.mkdir(parents=True)
    malformed_path.write_text(json.dumps({"provider_id": "openai"}), encoding="utf-8")

    with pytest.raises(OAuthCredentialStoreError, match="access_token"):
        store.load("openai")


def test_oauth_credential_delete_is_idempotent(tmp_path):
    store = OAuthCredentialStore(tmp_path / "oauth")
    store.save(OAuthCredential(provider_id="openai", access_token="placeholder"))

    assert store.delete("openai") is True
    assert store.delete("openai") is False
    assert store.load("openai") is None
