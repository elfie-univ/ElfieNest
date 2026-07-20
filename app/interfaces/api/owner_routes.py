"""Owner REST API — 用户 CRUD + LLM 配置读写。

所有端点通过 ``Depends(require_owner)`` 保护，密码字段永不出现于响应中。
``require_owner`` 是旧模块名兼容入口，当前语义为只允许 Owner。

Owner 精灵端点只提供公开元信息列表，不暴露私密聊天与配置内容。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.features.accounts.auth import (
    get_current_user,
    hash_password,
    require_owner,
)
from app.features.configuration.runtime_store import read_runtime_config, write_runtime_config
from app.infrastructure.persistence.store import get_db
from ai_runtime.storage.data_home import get_config_path

logger = logging.getLogger("app.interfaces.api.owner_routes")

__all__ = ("get_current_user", "require_owner", "router")

router = APIRouter(prefix="/api/owner", tags=["owner"])

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

# ===================================================================
# 用户管理
# ===================================================================


@router.post("/users", status_code=201)
async def create_user(
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    """创建新用户。

    Body: ``{"username": ..., "password": ..., "role": "user"}``
    返回 user 对象（**不含 password_hash**）。
    """
    _ = owner
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role", "user")

    if not username or not password:
        raise HTTPException(status_code=422, detail="用户名和密码不能为空")
    if role != "user":
        raise HTTPException(status_code=422, detail="role 必须是 user")

    db_path: str = request.app.state.db_path
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        )
        if cursor.fetchone() is not None:
            raise HTTPException(status_code=409, detail="用户名已存在")

        pw_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, pw_hash, role),
        )
        conn.commit()
        user_id = cursor.lastrowid

        cursor = conn.execute(
            "SELECT id, username, role, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()

    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "created_at": row["created_at"],
    }


@router.get("/users")
async def list_users(
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> list:
    """列出所有用户（排除当前登录的Owner自己）。

    ``elfie_count`` 通过子查询 ``SELECT COUNT(*) FROM elfie_registry WHERE owner_user_id = u.id``
    计算每个用户名下精灵数。
    """
    db_path: str = request.app.state.db_path
    current_user_id = owner["id"]
    with get_db(db_path) as conn:
        cursor = conn.execute("""
            SELECT u.id, u.username, u.role, u.created_at,
                   (SELECT COUNT(*)
                    FROM elfie_registry
                    WHERE owner_user_id = u.id) AS elfie_count
            FROM users u
            WHERE u.id != ?
            ORDER BY u.id
        """, (current_user_id,))
        rows = cursor.fetchall()

    return [
        {
            "id": r["id"],
            "username": r["username"],
            "role": r["role"],
            "created_at": r["created_at"],
            "elfie_count": r["elfie_count"],
        }
        for r in rows
    ]


@router.get("/elfies")
async def list_all_elfies(
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> list:
    _ = owner
    db_path: str = request.app.state.db_path
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT e.elfie_id,
                   e.name,
                   e.owner_user_id,
                   u.username AS owner_username,
                   e.species_id,
                   e.personality_style,
                   e.height,
                   e.build,
                   e.bed_id,
                   b.name AS bed_name,
                   r.id AS room_id,
                   r.name AS room_name,
                   e.created_at
            FROM elfie_registry e
            LEFT JOIN users u ON u.id = e.owner_user_id
            LEFT JOIN beds b ON b.id = e.bed_id
            LEFT JOIN rooms r ON r.id = b.room_id
            ORDER BY e.created_at DESC
            """,
        )
        rows = cursor.fetchall()

    return [
        {
            "elfie_id": row["elfie_id"],
            "name": row["name"],
            "owner_user_id": row["owner_user_id"],
            "owner_username": row["owner_username"],
            "species_id": row["species_id"],
            "personality_style": row["personality_style"],
            "height": row["height"],
            "build": row["build"],
            "bed_id": row["bed_id"],
            "bed_name": row["bed_name"],
            "room_id": row["room_id"],
            "room_name": row["room_name"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    """修改用户信息。

    Body 可选字段: ``username``, ``role``, ``password``。
    只传需要修改的字段，其他保持不变。
    """
    _ = owner
    db_path: str = request.app.state.db_path

    # 检查用户存在性，并保护唯一 Owner 不被用户管理接口改写。
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT id, role FROM users WHERE id = ?",
            (user_id,),
        )
        target = cursor.fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        if target["role"] == "owner":
            raise HTTPException(
                status_code=403,
                detail="Owner 账户只能通过本机 Owner 菜单恢复",
            )

    # 构建动态 UPDATE
    updates: list[str] = []
    params: list[Any] = []

    username = body.get("username")
    if username is not None:
        username = str(username).strip()
        if not username:
            raise HTTPException(status_code=422, detail="用户名不能为空")
        # 检查唯一性（排除自身）
        with get_db(db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (username, user_id),
            )
            if cursor.fetchone() is not None:
                raise HTTPException(status_code=409, detail="用户名已存在")
        updates.append("username = ?")
        params.append(username)

    role = body.get("role")
    if role is not None:
        if role != "user":
            raise HTTPException(status_code=422, detail="role 必须是 user")
        updates.append("role = ?")
        params.append(role)

    password = body.get("password")
    if password:
        pw_hash = hash_password(password)
        updates.append("password_hash = ?")
        params.append(pw_hash)

    if not updates:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")

    params.append(user_id)
    with get_db(db_path) as conn:
        if password:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT id, username, role, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()

    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "created_at": row["created_at"],
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    """删除用户。

    级联删除该用户名下的精灵（从 elfie_registry 删除记录）。
    精灵配置目录 ``~/.elfienest/elfies/<elfie_id>/`` 保留以便恢复。

    约束：**不能删除唯一的 owner 用户**。
    """
    _ = owner
    db_path: str = request.app.state.db_path

    # 检查用户存在性
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        # Owner 是系统唯一所有者，不能从 Web 用户管理中删除。
        if row["role"] == "owner":
            raise HTTPException(status_code=400, detail="不能删除 Owner 账户")

        # 级联删除精灵 + 删除用户
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute(
            "DELETE FROM elfie_registry WHERE owner_user_id = ?",
            (user_id,),
        )
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    logger.info("Owner deleted user %s (id=%d)", row["username"], user_id)
    return {"detail": f"用户 {row['username']} 已删除"}
# ===================================================================
# LLM 配置管理
# ===================================================================


@router.get("/config")
async def get_config(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    """读取 ``ELFIE_HOME/config.yaml``。

    文件可能不存在（gitignored 且尚未创建），此时返回 ``{}``。
    解析失败（非法 JSON）同样返回 ``{}``。
    """
    _ = owner
    return read_runtime_config(get_config_path())


@router.put("/config")
async def update_config(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    """写入 ``ELFIE_HOME/config.yaml``。

    操作步骤：
    1. 校验 JSON 必须包含 ``providers`` 字典结构
    2. 如果当前 YAML 存在，先创建同目录备份
    3. 写入新内容

    .. warning::
        修改配置可能影响所有精灵的 LLM 行为。
    """
    _ = owner
    # 校验
    if "providers" not in body or not isinstance(body["providers"], dict):
        raise HTTPException(
            status_code=400,
            detail="配置必须包含 providers 字典结构",
        )

    write_runtime_config(get_config_path(), body)
    logger.info("Runtime config updated by owner")
    return {"detail": "配置已更新"}
