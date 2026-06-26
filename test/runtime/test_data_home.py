"""tests for runtime.storage.data_home module"""
import os
import tempfile
from pathlib import Path

from runtime.storage.data_home import (
    get_elfie_home,
    get_config_path,
    get_env_path,
    get_db_path,
    get_elfie_config_dir,
    get_cache_dir,
    get_logs_dir,
    get_skills_dir,
    get_audio_cache_dir,
    get_sessions_dir,
    ensure_elfie_home,
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
    for subdir in ["elfies", "cache", "logs", "skills", "audio_cache", "sessions"]:
        assert (home / subdir).exists()


def test_path_helpers(monkeypatch, tmp_path):
    """各路径辅助函数返回正确路径"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "paths_test"))
    assert get_config_path() == get_elfie_home() / "config.yaml"
    assert get_env_path() == get_elfie_home() / ".env"
    assert get_db_path() == get_elfie_home() / "nest.db"
    assert get_elfie_config_dir("elfie_123") == get_elfie_home() / "elfies" / "elfie_123"
    assert get_cache_dir() == get_elfie_home() / "cache"
    assert get_logs_dir() == get_elfie_home() / "logs"
    assert get_skills_dir() == get_elfie_home() / "skills"
    assert get_audio_cache_dir() == get_elfie_home() / "audio_cache"
    assert get_sessions_dir() == get_elfie_home() / "sessions"
