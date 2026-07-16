"""测试辅助函数 — 直接在数据库中创建测试用户/管理员。

使用方式::

    from _helpers import create_test_admin, create_test_user

    admin_id = create_test_admin(db_path)
    user_id = create_test_user(db_path, "alice", "pass")
"""

from elfienest.persistence.store import get_db, hash_password


def create_test_admin(db_path: str, username: str = "admin", password: str = "adminchangeme") -> int:
    """直接在数据库中创建测试 Owner，绕过 setup wizard。

    Returns:
        新创建 Owner 的 user_id。
    """
    with get_db(db_path) as conn:
        pw_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            (username, pw_hash),
        )
        user_id = cursor.lastrowid
        conn.commit()
    return user_id


def create_test_user(db_path: str, username: str, password: str, role: str = "user") -> int:
    """直接在数据库中创建测试用户。

    Returns:
        新创建用户的 user_id。
    """
    with get_db(db_path) as conn:
        pw_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, pw_hash, role),
        )
        user_id = cursor.lastrowid
        conn.commit()
    return user_id
