"""tests for runtime.storage.migration module"""

import json
from pathlib import Path

import yaml

from runtime.storage.migration import (
    CURRENT_CONFIG_VERSION,
    _migrate_old_data_dir,
    _migrate_runtime_config_json,
    migrate_config,
    migrate_data_home,
)


def test_migrate_no_old_data(monkeypatch, tmp_path):
    """没有旧数据时，创建空的 ~/.elfienest/ 结构并生成默认 config.yaml"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "new_home"))
    # 确保项目根目录下也没有旧 data/ 和 runtime_config.json
    monkeypatch.setattr(
        "runtime.storage.migration._OLD_DATA_DIR", tmp_path / "nonexistent_data"
    )
    monkeypatch.setattr(
        "runtime.storage.migration._OLD_RUNTIME_CONFIG",
        tmp_path / "nonexistent_config.json",
    )
    result = migrate_data_home()
    assert result is True
    home = Path(tmp_path / "new_home")
    assert home.exists()
    assert (home / "config.yaml").exists()
    # 验证默认 config.yaml 包含 config_version
    with open(home / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert config.get("config_version") == CURRENT_CONFIG_VERSION


def test_migrate_already_migrated(monkeypatch, tmp_path):
    """已迁移（~/.elfienest/ 已存在且有内容）→ 直接返回 True"""
    home = tmp_path / "already_migrated"
    home.mkdir()
    (home / "config.yaml").write_text("config_version: 1\n", encoding="utf-8")
    monkeypatch.setenv("ELFIE_HOME", str(home))
    result = migrate_data_home()
    assert result is True


def test_migrate_preserves_old_data(tmp_path):
    """迁移后旧 data/ 目录仍然存在（不删除）"""
    old_data = tmp_path / "old_project" / "data"
    old_data.mkdir(parents=True)
    (old_data / "nest.db").write_text("fake db content", encoding="utf-8")
    elfies = old_data / "elfies"
    elfies.mkdir()
    (elfies / "test_elfie").mkdir()
    (elfies / "test_elfie" / "personality.yaml").write_text(
        "test: true", encoding="utf-8"
    )

    new_home = tmp_path / "elfienest"
    new_home.mkdir()

    _migrate_old_data_dir(old_data, new_home)

    # 旧目录仍然存在
    assert old_data.exists()
    assert (old_data / "nest.db").exists()
    # 新目录有数据
    assert (new_home / "nest.db").exists()
    assert (new_home / "elfies" / "test_elfie" / "personality.yaml").exists()


def test_migrate_config_version_1():
    """版本 1 配置迁移后 config_version 等于 CURRENT_CONFIG_VERSION"""
    config = {"config_version": 1, "providers": {}}
    result = migrate_config(config)
    assert result["config_version"] == CURRENT_CONFIG_VERSION


def test_runtime_config_json_conversion(tmp_path):
    """runtime_config.json → config.yaml 转换，自动添加 config_version"""
    # 创建旧的 runtime_config.json
    json_path = tmp_path / "runtime_config.json"
    config_data = {
        "providers": {
            "openai": {"api_key": "test", "api_base": "https://api.openai.com/v1"}
        },
        "system": {"llm": {"default_cheap_model": "gpt-4o-mini"}},
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    # _migrate_runtime_config_json 接收 home 目录，
    # 从 module-level _OLD_RUNTIME_CONFIG 读取 JSON，写入 home / "config.yaml"
    import runtime.storage.migration as migration_mod

    old_config_backup = migration_mod._OLD_RUNTIME_CONFIG
    try:
        migration_mod._OLD_RUNTIME_CONFIG = json_path
        new_home = tmp_path / "new_elfienest"
        new_home.mkdir()
        _migrate_runtime_config_json(new_home)

        yaml_path = new_home / "config.yaml"
        assert yaml_path.exists()
        with open(yaml_path, encoding="utf-8") as f:
            converted = yaml.safe_load(f)
        assert "config_version" in converted
        assert converted["config_version"] == CURRENT_CONFIG_VERSION
        assert "providers" in converted
        assert "api_key" not in converted["providers"]["openai"]
        assert converted["providers"]["openai"]["api_key_env"] == "OPENAI_API_KEY"
        assert "OPENAI_API_KEY=test" in (new_home / ".env").read_text(encoding="utf-8")
    finally:
        migration_mod._OLD_RUNTIME_CONFIG = old_config_backup
