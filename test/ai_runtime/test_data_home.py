"""tests for ai_runtime.storage.data_home module"""

import os
import stat
from pathlib import Path

import pytest

from ai_runtime.storage.data_home import (
    ensure_elfie_home,
    get_cache_dir,
    get_config_path,
    get_configs_dir,
    get_credentials_dir,
    get_db_path,
    get_elfie_config_dir,
    get_elfie_conversations_dir,
    get_elfie_developer_home,
    get_elfie_home,
    get_env_path,
    get_food_catalog_path,
    get_food_history_dir,
    get_logs_dir,
    get_model_validation_dir,
    get_oauth_credentials_dir,
    get_provider_catalog_path,
    get_provider_config_path,
    get_provider_validation_dir,
    get_reports_dir,
    get_runtime_config_paths,
    get_runtime_validation_dir,
    get_sessions_dir,
    get_skills_dir,
    get_tool_config_path,
)


def test_get_elfie_home_default(monkeypatch):
    """默认返回 ~/.elfienest/"""
    monkeypatch.delenv("ELFIE_HOME", raising=False)
    home = get_elfie_home()
    assert home == Path.home() / ".elfienest"


def test_get_elfie_home_env_override(monkeypatch, tmp_path):
    """ELFIE_HOME 环境变量覆盖默认路径"""
    custom = tmp_path / "custom_elfie"
    monkeypatch.setenv("ELFIE_HOME", str(custom))
    assert get_elfie_home() == custom


def test_ensure_elfie_home_creates_structure(monkeypatch, tmp_path):
    """ensure_elfie_home 创建所有子目录"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "test_elfie"))
    ensure_elfie_home()
    home = get_elfie_home()
    assert home.exists()
    for subdir in [
        "elfies",
        "cache",
        "logs",
        "skills",
        "sessions",
        "configs",
        "configs/credentials",
        "configs/credentials/oauth",
        "configs/food-packages-history",
        "reports",
        "reports/provider-validations",
        "reports/model-validations",
        "reports/runtime-validations",
    ]:
        assert (home / subdir).exists()


def test_path_helpers(monkeypatch, tmp_path):
    """各路径辅助函数返回正确路径"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "paths_test"))
    assert get_configs_dir() == get_elfie_home() / "configs"
    assert get_credentials_dir() == get_configs_dir() / "credentials"
    assert get_oauth_credentials_dir() == get_credentials_dir() / "oauth"
    assert get_reports_dir() == get_elfie_home() / "reports"
    assert get_provider_validation_dir() == get_reports_dir() / "provider-validations"
    assert get_model_validation_dir() == get_reports_dir() / "model-validations"
    assert get_runtime_validation_dir() == get_reports_dir() / "runtime-validations"
    assert get_config_path() == get_configs_dir() / "runtime.yaml"
    assert get_provider_config_path() == get_configs_dir() / "providers.yaml"
    assert get_provider_catalog_path() == get_configs_dir() / "provider-catalog.yaml"
    assert get_tool_config_path() == get_configs_dir() / "tools.yaml"
    assert get_runtime_config_paths() == (
        get_configs_dir() / "runtime.yaml",
        get_configs_dir() / "providers.yaml",
        get_configs_dir() / "tools.yaml",
    )
    assert get_food_catalog_path() == get_configs_dir() / "food-packages.yaml"
    assert get_food_history_dir() == get_configs_dir() / "food-packages-history"
    assert get_env_path() == get_credentials_dir() / "api-keys.env"
    assert get_db_path() == get_elfie_home() / "nest.db"
    assert (
        get_elfie_config_dir("elfie_123") == get_elfie_home() / "elfies" / "elfie_123"
    )
    assert get_cache_dir() == get_elfie_home() / "cache"
    assert get_logs_dir() == get_elfie_home() / "logs"
    assert get_skills_dir() == get_elfie_home() / "skills"
    assert get_sessions_dir() == get_elfie_home() / "sessions"


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose POSIX modes")
def test_ensure_elfie_home_secures_config_and_report_directories(
    monkeypatch,
    tmp_path,
):
    """配置、凭据和报告目录只允许当前用户访问。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "secure-home"))

    ensure_elfie_home()

    for directory in (
        get_configs_dir(),
        get_credentials_dir(),
        get_oauth_credentials_dir(),
        get_reports_dir(),
        get_provider_validation_dir(),
        get_model_validation_dir(),
        get_runtime_validation_dir(),
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_developer_home_is_independent_from_production_home(monkeypatch, tmp_path):
    """开发工具根只能由 ELFIE_DEV_HOME 控制。"""
    production_home = tmp_path / "production"
    developer_home = tmp_path / "developer"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))
    monkeypatch.setenv("ELFIE_DEV_HOME", str(developer_home))

    assert get_elfie_developer_home() == developer_home
    assert get_elfie_developer_home() != get_elfie_home()
    assert not production_home.exists()


def test_developer_home_defaults_to_sibling_hidden_directory(monkeypatch):
    """未配置时开发工具根不会落入生产根。"""
    monkeypatch.delenv("ELFIE_HOME", raising=False)
    monkeypatch.delenv("ELFIE_DEV_HOME", raising=False)

    assert get_elfie_developer_home() == Path.home() / ".elfienest-dev"
    assert get_elfie_developer_home() != get_elfie_home()


def test_elfie_conversation_path_rejects_path_traversal(monkeypatch, tmp_path):
    """精灵会话目录不得接受跳出生产根的 ID。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "production"))

    with pytest.raises(ValueError, match="精灵 ID"):
        get_elfie_conversations_dir("../escape")
