from __future__ import annotations

import yaml

from ai_runtime.storage.data_home import (
    get_config_path,
    get_provider_config_path,
    get_tool_config_path,
)
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
        "providers": {
            "openai": {
                "api_base": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            }
        },
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
    provider_document = yaml.safe_load(
        get_provider_config_path().read_text(encoding="utf-8")
    )
    tool_document = yaml.safe_load(get_tool_config_path().read_text(encoding="utf-8"))

    assert runtime_document["version"] == 1
    assert "providers" not in runtime_document
    assert "tools" not in runtime_document["runtime_policy"]
    assert provider_document == {
        "version": 1,
        "providers": composite["providers"],
    }
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
    initial = {
        "providers": {"ollama": {"api_base": "http://localhost:11434"}},
        "runtime_policy": {"tools": {"web_search": {"enabled": False}}},
    }
    write_runtime_config_bundle(initial)

    updated = {
        "providers": {"ollama": {"api_base": "http://localhost:22434"}},
        "runtime_policy": {"tools": {"web_search": {"enabled": True}}},
    }
    write_runtime_config_bundle(updated)

    for path in (
        get_config_path(),
        get_provider_config_path(),
        get_tool_config_path(),
    ):
        assert path.with_suffix(f"{path.suffix}.bak").exists()


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

    assert "provider-plaintext" not in get_provider_config_path().read_text(
        encoding="utf-8"
    )
    assert "tool-plaintext" not in get_tool_config_path().read_text(encoding="utf-8")
    restored = read_runtime_config_bundle()
    assert "api_key" not in restored["providers"]["openai"]
    assert "api_key" not in restored["runtime_policy"]["tools"]["web_search"]


def test_runtime_config_bundle_follows_current_elfie_home(
    monkeypatch,
    tmp_path,
) -> None:
    first_home = tmp_path / "first"
    second_home = tmp_path / "second"

    monkeypatch.setenv("ELFIE_HOME", str(first_home))
    write_runtime_config_bundle({"providers": {"first": {"api_base": "http://first"}}})

    monkeypatch.setenv("ELFIE_HOME", str(second_home))
    write_runtime_config_bundle(
        {"providers": {"second": {"api_base": "http://second"}}}
    )

    monkeypatch.setenv("ELFIE_HOME", str(first_home))
    assert "first" in read_runtime_config_bundle()["providers"]

    monkeypatch.setenv("ELFIE_HOME", str(second_home))
    config = read_runtime_config_bundle()
    assert "second" in config["providers"]
    assert "first" not in config["providers"]
