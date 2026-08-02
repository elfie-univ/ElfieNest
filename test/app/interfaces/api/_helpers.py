"""测试辅助函数 — 直接在数据库中创建测试用户/Owner。

使用方式::

    from _helpers import create_test_owner, create_test_user

    owner_id = create_test_owner(db_path)
    user_id = create_test_user(db_path, "alice", "pass")
"""

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
