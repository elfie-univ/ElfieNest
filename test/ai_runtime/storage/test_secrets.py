import os

import pytest

from ai_runtime.storage.data_home import get_credentials_dir, get_env_path
from ai_runtime.storage.secrets import (
    provider_secret_name,
    read_secrets,
    redact_secret,
    resolve_secret,
    set_provider_secret,
)


def test_provider_secret_name_uses_profile_and_custom_fallback():
    assert provider_secret_name("openai") == "OPENAI_API_KEY"
    assert provider_secret_name("my-gateway") == "MY_GATEWAY_API_KEY"


def test_set_provider_secret_round_trip_and_secure_mode(tmp_path):
    path = tmp_path / ".env"

    name = set_provider_secret("openai", "local-secret", path)

    assert name == "OPENAI_API_KEY"
    assert read_secrets(path)[name] == "local-secret"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_default_secret_path_secures_credentials_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "elfie-home"))

    set_provider_secret("openai", "local-secret")

    assert read_secrets(get_env_path())["OPENAI_API_KEY"] == "local-secret"
    if os.name != "nt":
        assert get_credentials_dir().stat().st_mode & 0o777 == 0o700
        assert get_env_path().stat().st_mode & 0o777 == 0o600


def test_environment_overrides_local_secret(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    set_provider_secret("openai", "file-secret", path)
    monkeypatch.setenv("OPENAI_API_KEY", "environment-secret")

    assert resolve_secret("OPENAI_API_KEY", path) == "environment-secret"


def test_secret_rejects_newlines_and_redacts_values(tmp_path):
    with pytest.raises(ValueError):
        set_provider_secret("openai", "bad\nsecret", tmp_path / ".env")
    assert redact_secret("abcdefgh") == "****efgh"
