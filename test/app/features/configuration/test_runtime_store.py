import os

import pytest

from ai_runtime.storage.data_home import (
    get_config_path,
    get_provider_config_path,
    get_tool_config_path,
)
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


def test_default_runtime_store_uses_split_production_documents(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    path = get_config_path()

    write_runtime_config(
        path,
        {
            "providers": {
                "openai": {
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "split-secret",
                }
            },
            "runtime_policy": {
                "task_routes": {"reasoning": "focus"},
                "tools": {"web_search": {"enabled": True}},
            },
        },
    )

    assert path.exists()
    assert not get_provider_config_path().exists()
    assert get_tool_config_path().exists()
    assert "providers" not in path.read_text(encoding="utf-8")

    restored = read_runtime_config(path)
    assert "providers" not in restored
    assert restored["runtime_policy"]["task_routes"]["reasoning"] == "focus"
    assert restored["runtime_policy"]["tools"]["web_search"]["enabled"] is True
