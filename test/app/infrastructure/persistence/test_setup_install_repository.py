"""Unit tests for SetupInstallRepository draft methods."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.setup_install_repository import (
    SetupDraftRecord,
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import init_db


def test_get_draft_returns_default_values_when_not_set(tmp_path: Path) -> None:
    """草稿未设置时返回默认值"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    draft = repo.get_draft()

    assert draft.owner_account_id is None
    assert draft.display_name is None
    assert draft.password_hash is None
    assert draft.use_local_ollama is None
    assert draft.model_id is None
    assert draft.bed_count is None
    assert draft.owner_configured is False
    assert draft.offline_configured is False
    assert draft.nest_configured is False
    assert draft.locked_at is None
    assert draft.password_configured is False
    assert draft.complete is False


def test_save_owner_draft_updates_json_field(tmp_path: Path) -> None:
    """保存 Owner 草稿更新 JSON 字段"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    draft = repo.save_owner_draft(
        account_id="testuser",
        display_name="测试用户",
        password_hash="hashed_secret",
    )

    # 验证返回值
    assert draft.owner_account_id == "testuser"
    assert draft.display_name == "测试用户"
    assert draft.password_hash == "hashed_secret"
    assert draft.owner_configured is True
    assert draft.password_configured is True

    # 验证数据库中的 JSON 字段
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT setup_draft_json FROM local_installations WHERE installation_id='local'"
        ).fetchone()
        assert row is not None
        assert row[0] is not None

        stored = json.loads(row[0])
        assert stored["owner_account_id"] == "testuser"
        assert stored["display_name"] == "测试用户"
        assert stored["password_hash"] == "hashed_secret"
        assert stored["owner_configured"] is True


def test_save_owner_draft_validates_empty_account_id(tmp_path: Path) -> None:
    """验证 account_id 不能为空"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    with pytest.raises(ValueError, match="账号不能为空"):
        repo.save_owner_draft(
            account_id="   ",  # 空白字符串
            display_name="Test",
            password_hash="secret",
        )


def test_save_owner_draft_validates_empty_password_hash(tmp_path: Path) -> None:
    """验证 password_hash 不能为空字符串"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    with pytest.raises(ValueError, match="密码哈希不能为空"):
        repo.save_owner_draft(
            account_id="testuser",
            display_name="Test",
            password_hash="",  # 空字符串
        )


def test_save_owner_draft_preserves_existing_password(tmp_path: Path) -> None:
    """保存时保留已有密码"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    # 第一次保存，设置密码
    repo.save_owner_draft(
        account_id="testuser",
        display_name="Test",
        password_hash="first_password",
    )

    # 第二次保存，不传密码
    draft = repo.save_owner_draft(
        account_id="testuser",
        display_name="Updated Name",
        password_hash=None,  # 不传密码
    )

    # 密码应该保留
    assert draft.password_hash == "first_password"


def test_save_offline_draft_without_ollama(tmp_path: Path) -> None:
    """不使用 Ollama 时正确保存"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    draft = repo.save_offline_draft(use_local_ollama=False, model_id=None)

    assert draft.use_local_ollama is False
    assert draft.model_id is None
    assert draft.offline_configured is True


def test_save_nest_draft_validates_minimum_bed_count(tmp_path: Path) -> None:
    """验证最小床位数（4）"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    with pytest.raises(ValueError, match="必须在 4 到 32 之间"):
        repo.save_nest_draft(bed_count=3)


def test_save_nest_draft_validates_maximum_bed_count(tmp_path: Path) -> None:
    """验证最大床位数（32）"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    with pytest.raises(ValueError, match="必须在 4 到 32 之间"):
        repo.save_nest_draft(bed_count=33)


def test_save_nest_draft_accepts_valid_range(tmp_path: Path) -> None:
    """接受有效范围内的床位数"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    # 测试边界值
    for bed_count in [4, 16, 32]:
        draft = repo.save_nest_draft(bed_count=bed_count)
        assert draft.bed_count == bed_count
        assert draft.nest_configured is True


def test_lock_draft_succeeds_with_complete_config(tmp_path: Path) -> None:
    """完整配置时可以锁定"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    # 准备完整的配置
    repo.save_owner_draft(
        account_id="owner",
        display_name="Owner",
        password_hash="secret",
    )
    repo.save_offline_draft(use_local_ollama=False, model_id=None)
    repo.save_nest_draft(bed_count=4)

    # 锁定
    locked = repo.lock_draft()
    assert locked is True

    # 验证 locked_at 已设置
    draft = repo.get_draft()
    assert draft.locked_at is not None


def test_lock_draft_fails_with_incomplete_config(tmp_path: Path) -> None:
    """不完整配置时无法锁定"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    # 只有 Owner 配置，缺少 offline 和 nest
    repo.save_owner_draft(
        account_id="owner",
        display_name="Owner",
        password_hash="secret",
    )

    with pytest.raises(ValueError, match="配置尚未完成"):
        repo.lock_draft()


def test_lock_draft_requires_password(tmp_path: Path) -> None:
    """锁定需要密码已设置"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    # 完整配置但没有密码
    repo.save_owner_draft(
        account_id="owner",
        display_name="Owner",
        password_hash=None,  # 没有密码
    )
    repo.save_offline_draft(use_local_ollama=False, model_id=None)
    repo.save_nest_draft(bed_count=4)

    with pytest.raises(ValueError, match="配置尚未完成"):
        repo.lock_draft()


def test_lock_draft_is_idempotent(tmp_path: Path) -> None:
    """锁定是幂等的"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    # 准备完整配置
    repo.save_owner_draft(
        account_id="owner",
        display_name="Owner",
        password_hash="secret",
    )
    repo.save_offline_draft(use_local_ollama=False, model_id=None)
    repo.save_nest_draft(bed_count=4)

    # 第一次锁定
    locked1 = repo.lock_draft()
    assert locked1 is True

    # 第二次锁定（应该返回 False，表示已经锁定）
    locked2 = repo.lock_draft()
    assert locked2 is False

    # locked_at 应该保持不变
    draft = repo.get_draft()
    first_locked_at = draft.locked_at

    repo.lock_draft()
    draft_after = repo.get_draft()
    assert draft_after.locked_at == first_locked_at


def test_incremental_updates_preserve_existing_data(tmp_path: Path) -> None:
    """增量更新保留已有数据"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    # 第一次：只设置 Owner
    repo.save_owner_draft(
        account_id="user1",
        display_name="User One",
        password_hash="pass1",
    )

    # 第二次：添加 offline 配置
    repo.save_offline_draft(use_local_ollama=True, model_id="qwen2.5:0.5b")

    # 第三次：添加 nest 配置
    repo.save_nest_draft(bed_count=8)

    # 验证所有数据都保留了
    draft = repo.get_draft()
    assert draft.owner_account_id == "user1"
    assert draft.display_name == "User One"
    assert draft.password_hash == "pass1"
    assert draft.use_local_ollama is True
    assert draft.model_id == "qwen2.5:0.5b"
    assert draft.bed_count == 8
    assert draft.owner_configured is True
    assert draft.offline_configured is True
    assert draft.nest_configured is True


def test_json_field_preserves_chinese_characters(tmp_path: Path) -> None:
    """正确保存中文字符"""
    db_path = init_db(str(tmp_path / "nest.db"))
    repo = SetupInstallRepository(db_path)

    chinese_name = "张三李四王五"

    draft = repo.save_owner_draft(
        account_id="chinese_user",
        display_name=chinese_name,
        password_hash="secret",
    )

    assert draft.display_name == chinese_name

    # 验证数据库中的 JSON 正确保存中文
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT setup_draft_json FROM local_installations WHERE installation_id='local'"
        ).fetchone()
        stored = json.loads(row[0])
        assert stored["display_name"] == chinese_name
