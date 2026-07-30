"""tests for ai_runtime.storage.data_home module"""

from pathlib import Path

import pytest

from ai_runtime.storage import data_home
from ai_runtime.storage.data_home import (
    ensure_elfie_home,
    get_cache_dir,
    get_config_path,
    get_db_path,
    get_elfie_config_dir,
    get_elfie_conversations_dir,
    get_elfie_developer_home,
    get_elfie_home,
    get_env_path,
    get_food_catalog_path,
    get_food_history_dir,
    get_local_files_dir,
    get_logs_dir,
    get_model_evidence_path,
    get_sessions_dir,
    get_skills_dir,
    get_validation_dir,
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
    for subdir in ["elfies", "cache", "logs", "skills", "sessions"]:
        assert (home / subdir).exists()


def test_path_helpers(monkeypatch, tmp_path):
    """各路径辅助函数返回正确路径"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "paths_test"))
    assert get_config_path() == get_elfie_home() / "config.yaml"
    assert get_env_path() == get_elfie_home() / ".env"
    assert get_db_path() == get_elfie_home() / "nest.db"
    assert (
        get_elfie_config_dir("elfie_123") == get_elfie_home() / "elfies" / "elfie_123"
    )
    assert get_cache_dir() == get_elfie_home() / "cache"
    assert get_logs_dir() == get_elfie_home() / "logs"
    assert get_skills_dir() == get_elfie_home() / "skills"
    assert get_sessions_dir() == get_elfie_home() / "sessions"


def test_legacy_runtime_path_helpers_keep_existing_layout(monkeypatch, tmp_path):
    """Given旧运行时 helper，When解析路径，Then仍返回现有顶层布局。"""
    # Given
    production_home = tmp_path / "legacy-production"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))

    # When / Then
    assert get_config_path() == production_home / "config.yaml"
    assert get_env_path() == production_home / ".env"
    assert get_food_catalog_path() == production_home / "foods.yaml"
    assert get_food_history_dir() == production_home / "food_history"
    assert get_validation_dir() == production_home / "validations"
    assert get_model_evidence_path() == production_home / "model_evidence.yaml"
    assert get_local_files_dir() == production_home / "files"
    assert not production_home.exists()


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


def test_final_config_and_report_resolvers_use_new_layout_without_writes(
    monkeypatch, tmp_path
):
    """Given最终数据根，When解析配置和报告路径，Then返回新布局且不创建目录。"""
    # Given
    production_home = tmp_path / "production"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))

    # When
    resolved = {
        "providers": data_home.get_final_providers_config_path(),
        "auth": data_home.get_final_auth_env_path(),
        "runtime_config": data_home.get_final_runtime_config_path(),
        "food_packages": data_home.get_final_food_packages_path(),
        "food_history": data_home.get_final_food_packages_history_dir(),
        "model_evidence": data_home.get_final_model_evidence_path(),
        "model_validations": data_home.get_final_model_validations_dir(),
        "runtime_validations": data_home.get_final_runtime_validations_dir(),
        "runtime_state": data_home.get_final_runtime_state_path(),
        "runtime_locks": data_home.get_final_runtime_locks_dir(),
        "logs": data_home.get_final_logs_dir(),
    }

    # Then
    assert resolved == {
        "providers": production_home / "configs" / "providers.yaml",
        "auth": production_home / "configs" / "auth.env",
        "runtime_config": production_home / "configs" / "runtime.yaml",
        "food_packages": production_home / "configs" / "food-packages.yaml",
        "food_history": production_home
        / "configs"
        / "food-packages-history",
        "model_evidence": production_home / "reports" / "model-evidence.yaml",
        "model_validations": production_home / "reports" / "model-validations",
        "runtime_validations": production_home / "reports" / "runtime-validations",
        "runtime_state": production_home / "runtime" / "runtime.json",
        "runtime_locks": production_home / "runtime" / "locks",
        "logs": production_home / "logs",
    }
    assert not production_home.exists()


def test_final_user_asset_resolvers_accept_only_numeric_user_ids(
    monkeypatch, tmp_path
):
    """Given用户 ID，When解析最终用户资产路径，Then只接受纯数字 ID。"""
    # Given
    production_home = tmp_path / "production"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))

    # When / Then
    assert (
        data_home.get_final_user_assets_dir("42")
        == production_home / "assets" / "users" / "42"
    )
    assert (
        data_home.get_final_user_avatar_path("42", "png")
        == production_home / "assets" / "users" / "42" / "avatar.png"
    )
    assert (
        data_home.get_final_user_files_dir("42")
        == production_home / "assets" / "users" / "42" / "files"
    )
    assert not production_home.exists()

    for invalid_user_id in ("", "alice", "../42", "42/7", "4.2"):
        with pytest.raises(ValueError, match="用户 ID"):
            data_home.get_final_user_assets_dir(invalid_user_id)

    for invalid_extension in ("../png", "png/escape", ".png"):
        with pytest.raises(ValueError, match="头像扩展名"):
            data_home.get_final_user_avatar_path("42", invalid_extension)


@pytest.mark.parametrize(("extension", "normalized"), (("PNG", "png"), ("JpEg", "jpeg"), ("WEBP", "webp")))
def test_final_user_avatar_extension_is_normalized(
    monkeypatch, tmp_path, extension, normalized
):
    """Given大小写混合的有效图片扩展名，When解析头像路径，Then统一输出小写。"""
    # Given
    production_home = tmp_path / "production"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))

    # When
    avatar_path = data_home.get_final_user_avatar_path("42", extension)

    # Then
    assert avatar_path == production_home / "assets" / "users" / "42" / f"avatar.{normalized}"


def test_final_user_avatar_rejects_unsupported_extensions(monkeypatch, tmp_path):
    """Given非图片扩展名，When解析头像路径，Then拒绝潜在可执行文件。"""
    # Given
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "production"))

    # When / Then
    for extension in ("php", "exe", "svg"):
        with pytest.raises(ValueError, match="头像扩展名"):
            data_home.get_final_user_avatar_path("42", extension)


def test_final_elfie_resolvers_accept_only_exact_eight_digit_ids(
    monkeypatch, tmp_path
):
    """Given最终精灵 ID，When解析工作区路径，Then只接受精确 8 位数字。"""
    # Given
    production_home = tmp_path / "production"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))
    elfie_id = "12345678"

    # When
    resolved = {
        "workspace": data_home.get_final_elfie_workspace_dir(elfie_id),
        "assets": data_home.get_final_elfie_assets_dir(elfie_id),
        "godot": data_home.get_final_elfie_godot_dir(elfie_id),
        "profile": data_home.get_final_elfie_profile_path(elfie_id),
        "skills": data_home.get_final_elfie_skills_dir(elfie_id),
        "history": data_home.get_final_elfie_history_path(elfie_id),
        "attachments": data_home.get_final_elfie_attachments_dir(elfie_id),
        "knowledge": data_home.get_final_elfie_knowledge_path(elfie_id),
        "daily": data_home.get_final_elfie_daily_memory_dir(elfie_id),
        "people": data_home.get_final_elfie_people_memory_dir(elfie_id),
        "concepts": data_home.get_final_elfie_concepts_memory_dir(elfie_id),
    }

    # Then
    workspace = production_home / "elfies" / elfie_id
    assert resolved == {
        "workspace": workspace,
        "assets": workspace / "assets",
        "godot": workspace / "godot",
        "profile": workspace / "profile" / "profile.yaml",
        "skills": workspace / "skills",
        "history": workspace / "conversations" / "history.sqlite",
        "attachments": workspace / "conversations" / "attachments",
        "knowledge": workspace / "memory" / "knowledge.sqlite",
        "daily": workspace / "memory" / "daily",
        "people": workspace / "memory" / "people",
        "concepts": workspace / "memory" / "concepts",
    }
    assert not production_home.exists()

    for invalid_elfie_id in ("elfie_x", "1234567", "123456789", "../12345678"):
        with pytest.raises(ValueError, match="精灵 ID"):
            data_home.get_final_elfie_workspace_dir(invalid_elfie_id)


def test_distinct_data_roots_rejects_resolved_production_dev_conflicts(
    monkeypatch, tmp_path
):
    """Given生产和开发根配置，When解析后相同，Then精确拒绝冲突。"""
    # Given
    same_home = tmp_path / "same"
    monkeypatch.setenv("ELFIE_HOME", str(same_home))
    monkeypatch.setenv("ELFIE_DEV_HOME", str(same_home / ".." / "same"))

    # When / Then
    with pytest.raises(ValueError, match="生产数据根.*开发工具数据根.*不能重叠"):
        data_home.ensure_distinct_data_roots()


@pytest.mark.parametrize(
    ("production_relative", "developer_relative"),
    (("production", "production/devtools"), ("developer/production", "developer")),
)
def test_distinct_data_roots_rejects_ancestor_descendant_overlap(
    tmp_path, production_relative, developer_relative
):
    """Given双向嵌套的数据根，When校验隔离，Then拒绝祖先与后代重叠。"""
    # Given
    production_home = tmp_path / production_relative
    developer_home = tmp_path / developer_relative

    # When / Then
    with pytest.raises(ValueError, match="不能重叠"):
        data_home.assert_distinct_data_roots(production_home, developer_home)


def test_distinct_data_roots_rejects_symlink_equivalence(tmp_path):
    """Given指向生产根的开发根软链接，When校验隔离，Then拒绝等价路径。"""
    # Given
    production_home = tmp_path / "production"
    developer_home = tmp_path / "developer"
    production_home.mkdir()
    developer_home.symlink_to(production_home, target_is_directory=True)

    # When / Then
    with pytest.raises(ValueError, match="不能重叠"):
        data_home.assert_distinct_data_roots(production_home, developer_home)
