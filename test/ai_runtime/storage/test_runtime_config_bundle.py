from __future__ import annotations

import yaml

from ai_runtime.storage.data_home import (
    get_config_path,
    get_provider_config_path,
    get_tool_config_path,
)
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.runtime_config_bundle import (
    read_runtime_config_bundle,
    write_runtime_config_bundle,
)


def test_runtime_config_bundle_splits_and_reassembles_public_shape(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    composite = {
        "config_version": 2,
        "models": {"openai/gpt-test": {"visible": True}},
        "runtime_policy": {
            "task_routes": {"reasoning": "focus"},
            "tool_permissions": {"RUN_SKILL": {"mode": "allow"}},
            "tools": {
                "web_search": {
                    "enabled": True,
                    "provider": "tavily",
                    "max_results": 4,
                }
            },
        },
    }

    write_runtime_config_bundle(composite)

    runtime_document = yaml.safe_load(get_config_path().read_text(encoding="utf-8"))
    tool_document = yaml.safe_load(get_tool_config_path().read_text(encoding="utf-8"))

    assert runtime_document["version"] == 1
    assert "providers" not in runtime_document
    assert "tools" not in runtime_document["runtime_policy"]
    assert not get_provider_config_path().exists()
    assert tool_document == {
        "version": 1,
        "tools": composite["runtime_policy"]["tools"],
    }
    assert read_runtime_config_bundle() == composite


def test_runtime_config_bundle_creates_a_backup_for_each_existing_document(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    provider_store = ProviderConnectionStore()
    provider_store.create(catalog_id="ollama", alias="Ollama")
    provider_bytes = get_provider_config_path().read_bytes()
    initial = {
        "runtime_policy": {"tools": {"web_search": {"enabled": False}}},
    }
    write_runtime_config_bundle(initial)

    updated = {
        "runtime_policy": {"tools": {"web_search": {"enabled": True}}},
    }
    write_runtime_config_bundle(updated)

    assert not get_config_path().with_suffix(".yaml.bak").exists()
    assert get_tool_config_path().with_suffix(".yaml.bak").exists()
    assert not get_provider_config_path().with_suffix(".yaml.bak").exists()
    assert get_provider_config_path().read_bytes() == provider_bytes


def test_runtime_config_bundle_never_persists_plaintext_api_keys(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    write_runtime_config_bundle(
        {
            "providers": {
                "openai": {
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "provider-plaintext",
                }
            },
            "runtime_policy": {
                "tools": {
                    "web_search": {
                        "enabled": True,
                        "api_key": "tool-plaintext",
                    }
                }
            },
        }
    )

    assert not get_provider_config_path().exists()
    assert "tool-plaintext" not in get_tool_config_path().read_text(encoding="utf-8")
    restored = read_runtime_config_bundle()
    assert "providers" not in restored
    assert "api_key" not in restored["runtime_policy"]["tools"]["web_search"]


def test_runtime_config_bundle_follows_current_elfie_home(
    monkeypatch,
    tmp_path,
) -> None:
    first_home = tmp_path / "first"
    second_home = tmp_path / "second"

    monkeypatch.setenv("ELFIE_HOME", str(first_home))
    write_runtime_config_bundle({"system": {"marker": "first"}})

    monkeypatch.setenv("ELFIE_HOME", str(second_home))
    write_runtime_config_bundle({"system": {"marker": "second"}})

    monkeypatch.setenv("ELFIE_HOME", str(first_home))
    assert read_runtime_config_bundle()["system"]["marker"] == "first"

    monkeypatch.setenv("ELFIE_HOME", str(second_home))
    config = read_runtime_config_bundle()
    assert config["system"]["marker"] == "second"


def test_unchanged_tool_document_is_not_rewritten(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    write_runtime_config_bundle(
        {
            "system": {"appearance": {"theme": "light"}},
            "runtime_policy": {"tools": {"web_search": {"enabled": True}}},
        }
    )
    tool_path = get_tool_config_path()
    original_inode = tool_path.stat().st_ino
    original_bytes = tool_path.read_bytes()

    write_runtime_config_bundle(
        {
            "system": {"appearance": {"theme": "dark"}},
            "runtime_policy": {"tools": {"web_search": {"enabled": True}}},
        }
    )

    assert tool_path.stat().st_ino == original_inode
    assert tool_path.read_bytes() == original_bytes
