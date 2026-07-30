"""生产配置数据边界的基线与目标测试。

这些测试故意把旧配置文件放在 ``tmp_path``，通过 monkeypatch 模拟仓库中的
``runtime/runtime_config.json``，从而避免读写真实工作区状态。
"""

import importlib
import json
from pathlib import Path

import yaml

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.storage.data_home import get_config_path, get_elfie_home


def _write_legacy_runtime_config(path: Path, provider_id: str = "legacy_only") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "providers": {
                    provider_id: {
                        "api_base": "https://legacy.invalid/v1",
                        "api_mode": "chat_completions",
                        "status": "active",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _patch_legacy_runtime_path(monkeypatch, legacy_path: Path) -> None:
    config_module = importlib.import_module("ai_runtime.config")
    fake_module_file = legacy_path.parent / "config.py"
    monkeypatch.setattr(config_module, "__file__", str(fake_module_file))


def test_isolated_home_does_not_read_legacy_json(monkeypatch, tmp_path):
    """Given 隔离 ELFIE_HOME 且无 YAML，When 加载配置，Then 不读取旧 JSON。"""
    isolated_home = tmp_path / "isolated-home"
    legacy_path = tmp_path / "runtime" / "runtime_config.json"
    _write_legacy_runtime_config(legacy_path)
    _patch_legacy_runtime_path(monkeypatch, legacy_path)
    monkeypatch.setenv("ELFIE_HOME", str(isolated_home))

    # When: 读取当前生产配置。
    config = LLMRuntimeConfig.load()

    # Then: 路径解析已隔离，legacy JSON 不得进入正常配置。
    assert get_elfie_home() == isolated_home
    assert get_config_path() == isolated_home / "configs" / "runtime.yaml"
    assert not get_config_path().exists()
    assert "legacy_only" not in config.providers


def test_normal_load_does_not_read_legacy_runtime_json(monkeypatch, tmp_path):
    """Given 只有 legacy JSON，When 正常加载，Then 不应读取旧配置文件。"""
    isolated_home = tmp_path / "isolated-home"
    legacy_path = tmp_path / "runtime" / "runtime_config.json"
    _write_legacy_runtime_config(legacy_path)
    _patch_legacy_runtime_path(monkeypatch, legacy_path)
    monkeypatch.setenv("ELFIE_HOME", str(isolated_home))

    # When: 不调用任何迁移命令，直接创建运行时配置。
    config = LLMRuntimeConfig.load()

    # Then: 目标边界要求 legacy provider 不得进入正常配置。
    provider_ids = tuple(config.providers)
    assert "legacy_only" not in provider_ids
    assert not get_config_path().exists()


def test_malformed_yaml_does_not_trigger_legacy_fallback(monkeypatch, tmp_path):
    """Given 损坏 YAML 和有效 legacy JSON，When 正常加载，Then 不应回退到旧 JSON。"""
    isolated_home = tmp_path / "isolated-home"
    config_path = isolated_home / "configs" / "runtime.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("providers: [broken\n", encoding="utf-8")
    legacy_path = tmp_path / "runtime" / "runtime_config.json"
    _write_legacy_runtime_config(legacy_path, provider_id="legacy_after_bad_yaml")
    _patch_legacy_runtime_path(monkeypatch, legacy_path)
    monkeypatch.setenv("ELFIE_HOME", str(isolated_home))

    # When: YAML 解析失败时仍走正常配置加载路径。
    config = LLMRuntimeConfig.load()

    # Then: 损坏的当前配置不能把加载流程导向 legacy JSON。
    provider_ids = tuple(config.providers)
    assert "legacy_after_bad_yaml" not in provider_ids


def test_malformed_legacy_json_is_ignored_without_side_effects(monkeypatch, tmp_path):
    """Given 损坏 legacy JSON，When 正常加载，Then 返回默认配置且不创建 home 文件。"""
    isolated_home = tmp_path / "isolated-home"
    legacy_path = tmp_path / "runtime" / "runtime_config.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text('{"providers":', encoding="utf-8")
    _patch_legacy_runtime_path(monkeypatch, legacy_path)
    monkeypatch.setenv("ELFIE_HOME", str(isolated_home))

    # When: 解析损坏的旧 JSON。
    config = LLMRuntimeConfig.load()

    # Then: 解析失败被隔离，且不会隐式初始化或写入生产数据目录。
    provider_ids = tuple(config.providers)
    assert "legacy_only" not in provider_ids
    assert not isolated_home.exists()


def test_existing_config_yaml_is_authoritative_over_legacy(monkeypatch, tmp_path):
    """Given 已有 providers.yaml 和旧 JSON，When 正常加载，Then 只使用当前 Provider 配置。"""
    isolated_home = tmp_path / "isolated-home"
    provider_path = isolated_home / "configs" / "providers.yaml"
    provider_path.parent.mkdir(parents=True)
    
    from ai_runtime.storage.provider_connections import (
        ProviderConnection,
        ProviderConnectionDocument,
        ProviderConnectionStore,
    )
    
    store = ProviderConnectionStore(provider_path)
    store.save(
        ProviderConnectionDocument(
            connections={
                "custom_openai_0001": ProviderConnection(
                    connection_id="custom_openai_0001",
                    catalog_id="custom_openai",
                    alias="Current Provider",
                    api_base="https://current.invalid/v1",
                    api_mode="chat_completions",
                    enabled=True,
                )
            }
        )
    )
    
    legacy_path = tmp_path / "runtime" / "runtime_config.json"
    _write_legacy_runtime_config(legacy_path, provider_id="stale_legacy")
    _patch_legacy_runtime_path(monkeypatch, legacy_path)
    monkeypatch.setenv("ELFIE_HOME", str(isolated_home))

    # When: 读取已有当前配置。
    config = LLMRuntimeConfig.load()

    # Then: 当前 providers.yaml 是唯一来源，不被 legacy 状态污染。
    assert config.providers["custom_openai_0001"]["api_base"] == "https://current.invalid/v1"
    provider_ids = tuple(config.providers)
    assert "stale_legacy" not in provider_ids


def test_normal_load_does_not_migrate_old_data_directory(monkeypatch, tmp_path):
    """Given 旧 data 目录，When 正常加载，Then 不应隐式复制或初始化 home。"""
    isolated_home = tmp_path / "isolated-home"
    old_data = tmp_path / "old-install" / "data"
    old_data.mkdir(parents=True)
    (old_data / "nest.db").write_text("legacy-db", encoding="utf-8")
    _patch_legacy_runtime_path(monkeypatch, tmp_path / "missing-runtime_config.json")
    monkeypatch.setenv("ELFIE_HOME", str(isolated_home))

    # When: 只执行普通运行时配置加载。
    LLMRuntimeConfig.load()

    # Then: 旧 data 保持原位，普通加载不创建迁移目标目录。
    assert old_data.exists()
    assert (old_data / "nest.db").read_text(encoding="utf-8") == "legacy-db"
    assert not isolated_home.exists()


def test_runtime_api_reads_current_elfie_home_after_environment_switch(
    monkeypatch, tmp_path
):
    """Given two homes, When ELFIE_HOME changes, Then API helpers follow it."""
    from ai_runtime.storage.config_store import write_yaml_mapping
    from app.interfaces.api import runtime_routes

    first_home = tmp_path / "first"
    second_home = tmp_path / "second"
    write_yaml_mapping(
        first_home / "configs" / "runtime.yaml",
        {"providers": {"first": {"api_base": "http://first"}}},
    )
    write_yaml_mapping(
        second_home / "configs" / "runtime.yaml",
        {"providers": {"second": {"api_base": "http://second"}}},
    )

    monkeypatch.setenv("ELFIE_HOME", str(first_home))
    assert "first" in runtime_routes._read_runtime_config()["providers"]

    monkeypatch.setenv("ELFIE_HOME", str(second_home))
    config = runtime_routes._read_runtime_config()
    assert "second" in config["providers"]
    assert "first" not in config["providers"]
