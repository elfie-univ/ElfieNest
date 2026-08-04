"""tests for ai_runtime.storage.data_home module"""

import os
import stat
from pathlib import Path

import pytest

from ai_runtime.storage import data_home
from ai_runtime.storage.data_home import (
    data_home_from_db_path,
    ensure_elfie_home,
    get_config_path,
    get_configs_dir,
    get_credentials_dir,
    get_db_path,
    get_elfie_conversations_dir,
    get_elfie_developer_home,
    get_elfie_home,
    get_env_path,
    get_local_files_dir,
    get_model_validation_dir,
    get_reports_dir,
    get_runtime_locks_dir,
    get_runtime_state_path,
    get_runtime_validation_dir,
    get_skills_dir,
)


def test_explicit_data_home_overrides_environment(monkeypatch, tmp_path):
    """Given 显式路径和环境变量，When 解析数据根，Then 显式路径优先。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "environment"))

    selected = data_home.resolve_elfie_home(
        "explicit",
        invoking_cwd=tmp_path,
        runtime_mode="development",
        source_root=tmp_path / "source",
    )

    assert selected == (tmp_path / "explicit").resolve()


def test_environment_data_home_overrides_source_default(monkeypatch, tmp_path):
    """Given ELFIE_HOME，When 源码模式解析数据根，Then 环境变量优先。"""
    environment_home = tmp_path / "environment"
    monkeypatch.setenv("ELFIE_HOME", str(environment_home))

    selected = data_home.resolve_elfie_home(
        runtime_mode="development",
        source_root=tmp_path / "source",
    )

    assert selected == environment_home.resolve()


def test_source_mode_defaults_to_worktree_local_home(monkeypatch, tmp_path):
    """Given 无覆盖值，When 源码模式解析数据根，Then 使用当前 worktree 本地根。"""
    monkeypatch.delenv("ELFIE_HOME", raising=False)
    source_root = tmp_path / "worktree"

    selected = data_home.resolve_elfie_home(
        runtime_mode="development",
        source_root=source_root,
    )

    assert selected == (source_root / ".elfienest.local").resolve()


def test_release_mode_defaults_to_user_production_home(monkeypatch):
    """Given 无覆盖值，When 正式模式解析数据根，Then 使用用户生产根。"""
    monkeypatch.delenv("ELFIE_HOME", raising=False)

    selected = data_home.resolve_elfie_home(runtime_mode="release")

    assert selected == (Path.home() / ".elfienest").resolve()


def test_select_data_home_publishes_selected_root(monkeypatch, tmp_path):
    """Given 显式路径，When 选择数据根，Then 后续路径助手共享同一根。"""
    monkeypatch.delenv("ELFIE_HOME", raising=False)

    selected = data_home.select_elfie_home(
        "selected",
        invoking_cwd=tmp_path,
        runtime_mode="development",
        source_root=tmp_path / "source",
    )

    assert data_home.get_elfie_home() == selected
    assert data_home.get_db_path() == selected / "nest.db"
    assert data_home.get_logs_dir() == selected / "logs"


def test_database_path_resolves_through_the_shared_data_home_policy(tmp_path):
    """Given a database path, When callers need its root, Then one resolver owns it."""
    database = tmp_path / "selected" / "nest.db"

    resolved = data_home_from_db_path(database)

    assert resolved == database.parent.resolve()


def test_data_home_rejects_existing_file(tmp_path):
    """Given 文件路径，When 解析数据根，Then 拒绝把文件当作目录。"""
    target = tmp_path / "not-a-directory"
    target.write_text("x", encoding="utf-8")

    with pytest.raises(data_home.DataHomeSelectionError, match="不是目录"):
        data_home.resolve_elfie_home(str(target), invoking_cwd=tmp_path)


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
    """Given 空生产根，When ensure，Then 只创建最终共享目录。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "test_elfie"))
    ensure_elfie_home()
    home = get_elfie_home()
    actual = {path.relative_to(home) for path in home.rglob("*") if path.is_dir()}
    assert actual == {
        Path("assets"),
        Path("assets/users"),
        Path("configs"),
        Path("configs/credentials"),
        Path("elfies"),
        Path("logs"),
        Path("reports"),
        Path("reports/model-validations"),
        Path("reports/runtime-validations"),
        Path("runtime"),
        Path("runtime/locks"),
    }


def test_path_helpers(monkeypatch, tmp_path):
    """Given 生产根，When 解析共享路径，Then 全部来自 FinalRootLayout。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "paths_test"))
    assert get_config_path() == get_elfie_home() / "configs" / "runtime.yaml"
    assert get_env_path() == get_elfie_home() / "configs" / "auth.env"
    assert get_db_path() == get_elfie_home() / "nest.db"
    assert (
        get_model_validation_dir() == get_elfie_home() / "reports" / "model-validations"
    )
    assert (
        get_runtime_validation_dir()
        == get_elfie_home() / "reports" / "runtime-validations"
    )
    assert get_runtime_state_path() == get_elfie_home() / "runtime" / "runtime.json"
    assert get_runtime_locks_dir() == get_elfie_home() / "runtime" / "locks"
    assert (
        get_local_files_dir("42")
        == get_elfie_home() / "assets" / "users" / "42" / "files"
    )
    assert (
        get_skills_dir("00000042")
        == get_elfie_home() / "elfies" / "00000042" / "skills"
    )


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
        get_reports_dir(),
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

    with pytest.raises(ValueError, match="exactly eight ASCII digits"):
        get_elfie_conversations_dir("../escape")
