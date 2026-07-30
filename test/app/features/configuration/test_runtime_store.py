import os

import pytest

from app.features.configuration.runtime_store import (
    hydrate_runtime_secrets,
    read_runtime_config,
    write_runtime_config,
)


def test_yaml_runtime_store_splits_provider_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    path = tmp_path / "configs" / "runtime.yaml"

    write_runtime_config(
        path,
        {
            "providers": {
                "openai": {
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "local-secret",
                }
            }
        },
    )

    stored = path.read_text(encoding="utf-8")
    secret_path = tmp_path / "configs" / "auth.env"
    secret_file = secret_path.read_text(encoding="utf-8")
    assert "local-secret" not in stored
    assert "api_key_env: OPENAI_API_KEY" in stored
    assert "OPENAI_API_KEY=local-secret" in secret_file
    if os.name != "nt":
        assert secret_path.stat().st_mode & 0o777 == 0o600

    safe = read_runtime_config(path)
    assert "api_key" not in safe["providers"]["openai"]
    hydrated = hydrate_runtime_secrets(safe)
    assert hydrated["providers"]["openai"]["api_key"] == "local-secret"


def test_json_runtime_store_is_rejected_outside_explicit_migration(tmp_path):
    path = tmp_path / "runtime_config.json"
    config = {"providers": {"openai": {"api_key": "legacy-secret"}}}

    with pytest.raises(RuntimeError, match="拒绝"):
        write_runtime_config(path, config)

    with pytest.raises(RuntimeError, match="拒绝"):
        read_runtime_config(path)
