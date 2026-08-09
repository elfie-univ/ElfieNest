"""测试辅助函数 — 直接在数据库中创建测试用户/Owner。

使用方式::

    from _helpers import create_test_owner, create_test_user

    owner_id = create_test_owner(db_path)
    user_id = create_test_user(db_path, "alice", "pass")
"""

from typing import Any, Optional

from app.features.adoption.service import AdoptionRequest, adopt_elfie_for_user
from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import get_db, hash_password


def create_test_owner(
    db_path: str, account_id: str = "owner", password: str = "ownerchangeme"
) -> int:
    """直接在数据库中创建测试 Owner，绕过 setup wizard。

    Returns:
        新创建 Owner 的 user_id。
    """
    with get_db(db_path) as conn:
        pw_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, 'owner')",
            (account_id, pw_hash),
        )
        user_id = cursor.lastrowid
        conn.commit()
    return user_id


def create_test_user(
    db_path: str, account_id: str, password: str, role: str = "user"
) -> int:
    """直接在数据库中创建测试用户。

    Returns:
        新创建用户的 user_id。
    """
    with get_db(db_path) as conn:
        pw_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, ?)",
            (account_id, pw_hash, role),
        )
        user_id = cursor.lastrowid
        conn.commit()
    return user_id


def adopt_test_elfie(
    db_path: str,
    user_id: int,
    *,
    name: str = "小白",
    species_id: str = "fox",
    personality_style: str = "好奇探索",
    height: str = "standard",
    build: str = "standard",
    appearance_overrides: Optional[dict[str, Any]] = None,
    engine: Any = None,
) -> str:
    """通过正式 Adoption 服务创建测试精灵，不依赖已退役 HTTP 入口。"""
    result = adopt_elfie_for_user(
        db_path,
        user_id=user_id,
        request=AdoptionRequest(
            name=name,
            species_id=species_id,
            personality_style=personality_style,
            height=height,
            build=build,
            appearance_overrides=appearance_overrides or {},
        ),
        engine=engine,
    )
    return result.elfie_id


def complete_test_setup(db_path: str, *, bed_count: int = 8) -> None:
    """Complete Setup through the canonical installation phases."""
    repository = SetupInstallRepository(db_path)
    repository.save_offline_draft(use_local_ollama=False, model_id=None)
    repository.save_nest_draft(bed_count=bed_count)
    repository.begin_or_resume()
    for phase in range(2, 6):
        repository.complete_phase(phase=phase)
