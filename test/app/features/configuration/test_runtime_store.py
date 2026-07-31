import pytest

from ai_runtime.storage.config_store import ConfigStoreError
from ai_runtime.storage.data_home import (
    get_config_path,
    get_provider_config_path,
    get_tool_config_path,
)
from app.features.configuration.runtime_store import (
    read_runtime_config,
    write_runtime_config,
)


def test_custom_yaml_runtime_store_rejects_provider_payloads(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    path = tmp_path / "runtime-lab" / "config.yaml"

    with pytest.raises(ConfigStoreError, match="providers"):
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

    assert not path.exists()


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

    with pytest.raises(ConfigStoreError, match="providers"):
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

    assert not path.exists()
    assert not get_provider_config_path().exists()
    assert not get_tool_config_path().exists()
