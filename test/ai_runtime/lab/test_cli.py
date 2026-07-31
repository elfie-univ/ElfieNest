from __future__ import annotations

from ai_runtime.lab.cli import RuntimeLab
from ai_runtime.storage.data_home import (
    get_env_path,
    get_provider_config_path,
)
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.runtime_settings import read_runtime_settings
from ai_runtime.storage.secrets import read_secrets


def test_default_runtime_lab_writes_only_runtime_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    lab = RuntimeLab(input_fn=lambda _prompt: "", output_fn=lambda _message: None)

    payload = lab.config.to_safe_dict()
    payload["temperature"] = 0.25
    lab._write_runtime_config(payload)

    settings = read_runtime_settings()
    assert settings["temperature"] == 0.25
    assert "providers" not in settings
    assert not get_provider_config_path().exists()


def test_default_runtime_lab_saves_and_deletes_provider_connection(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    messages: list[str] = []
    lab = RuntimeLab(
        input_fn=lambda _prompt: "DELETE",
        output_fn=messages.append,
    )
    provider = {
        "display_name": "工作 OpenAI",
        "api_base": "https://api.openai.com/v1",
        "api_mode": "chat_completions",
        "auth_type": "bearer",
        "models": [{"id": "gpt-test", "display_name": "GPT Test"}],
    }

    lab._commit_provider("openai", provider, "test-secret")

    document = ProviderConnectionStore().load()
    connection = document.connections["openai_api_0001"]
    assert connection.catalog_id == "openai_api"
    assert connection.alias == "工作 OpenAI"
    assert connection.models[0].endpoint_model_id == "gpt-test"
    assert read_secrets(get_env_path())[connection.credential_ref] == "test-secret"

    assert lab._delete_provider(connection.connection_id) is True
    assert ProviderConnectionStore().load().connections == {}
    assert connection.credential_ref not in read_secrets(get_env_path())


def test_default_runtime_lab_allows_multiple_connections_for_one_product(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    lab = RuntimeLab(input_fn=lambda _prompt: "", output_fn=lambda _message: None)
    first = {
        "display_name": "工作账号",
        "api_base": "https://api.openai.com/v1",
        "api_mode": "chat_completions",
        "auth_type": "bearer",
        "models": [],
    }
    second = {**first, "display_name": "个人账号"}

    lab._commit_provider("openai", first, "work-secret")
    lab._commit_provider("openai", second, "personal-secret")

    connections = ProviderConnectionStore().load().connections
    assert list(connections) == ["openai_api_0001", "openai_api_0002"]
    assert connections["openai_api_0001"].alias == "工作账号"
    assert connections["openai_api_0002"].alias == "个人账号"
