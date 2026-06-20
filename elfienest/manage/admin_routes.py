"""管理员 REST API — 用户 CRUD + 精灵查看/编辑/删除（无创建）+ LLM 配置读写。

所有端点通过 ``Depends(require_admin)`` 保护，密码字段永不出现于响应中。

精灵**不能由管理员创建**（领养系统已替代），因此不实现 ``POST /api/admin/elfies``。
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from .auth import hash_password, verify_session
from .store import get_db

logger = logging.getLogger("elfienest.manage.admin_routes")

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
"""项目根目录（admin_routes.py → elfienest/manage/ → elfienest/ → 项目根）。"""

_RUNTIME_CONFIG_PATH: Path = _PROJECT_ROOT / "runtime" / "runtime_config.json"
"""``runtime_config.json`` 的完整路径（gitignored）。"""

# ---------------------------------------------------------------------------
# 鉴权依赖
# ---------------------------------------------------------------------------


def get_current_user(request: Request) -> Dict[str, Any]:
    """从 cookie ``session_token`` 获取当前用户。

    使用 ``request.app.state.db_path``（由 ``create_app`` 注入），
    与 ``app.py`` 中的本地 ``get_current_user`` 逻辑一致。
    """
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="未登录，缺少会话 token")

    user = verify_session(token, request.app.state.db_path)
    if user is None:
        raise HTTPException(status_code=401, detail="会话无效或已过期")

    return user


def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """要求当前用户为管理员。

    FastAPI 依赖链：``require_admin`` → ``get_current_user`` → 解析 cookie。
    非管理员用户触发 403，未登录触发 401。
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ===================================================================
# 用户管理
# ===================================================================


@router.post("/users", status_code=201)
async def create_user(
    body: Dict[str, Any],
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """创建新用户。

    Body: ``{"username": ..., "password": ..., "role": "admin"|"user"}``
    返回 user 对象（**不含 password_hash**）。
    """
    _ = admin
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role", "user")

    if not username or not password:
        raise HTTPException(status_code=422, detail="用户名和密码不能为空")
    if role not in ("admin", "user"):
        raise HTTPException(status_code=422, detail="role 必须是 admin 或 user")

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
    admin: Dict[str, Any] = Depends(require_admin),
) -> list:
    """列出所有用户（id, username, role, created_at, elfie_count）。

    ``elfie_count`` 通过子查询 ``SELECT COUNT(*) FROM elfie_registry WHERE owner_user_id = u.id``
    计算每个用户名下精灵数。
    """
    _ = admin
    db_path: str = request.app.state.db_path
    with get_db(db_path) as conn:
        cursor = conn.execute("""
            SELECT u.id, u.username, u.role, u.created_at,
                   (SELECT COUNT(*)
                    FROM elfie_registry
                    WHERE owner_user_id = u.id) AS elfie_count
            FROM users u
            ORDER BY u.id
        """)
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


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: Dict[str, Any],
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """修改用户信息。

    Body 可选字段: ``username``, ``role``, ``password``。
    只传需要修改的字段，其他保持不变。
    """
    _ = admin
    db_path: str = request.app.state.db_path

    # 检查用户存在性
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT id FROM users WHERE id = ?",
            (user_id,),
        )
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="用户不存在")

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
        if role not in ("admin", "user"):
            raise HTTPException(status_code=422, detail="role 必须是 admin 或 user")
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
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """删除用户。

    级联操作：将该用户名下精灵的 ``owner_user_id`` 置为 ``NULL``（精灵保留，变为未分配）。
    约束：**不能删除唯一的 admin 用户**。
    """
    _ = admin
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

        # 不能删除唯一的 admin
        if row["role"] == "admin":
            cursor = conn.execute(
                "SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'",
            )
            admin_count = cursor.fetchone()["cnt"]
            if admin_count <= 1:
                raise HTTPException(
                    status_code=400, detail="不能删除唯一的管理员"
                )

        # 级联清空精灵 owner + 删除用户
        conn.execute(
            "UPDATE elfie_registry SET owner_user_id = NULL WHERE owner_user_id = ?",
            (user_id,),
        )
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    logger.info("Admin deleted user %s (id=%d)", row["username"], user_id)
    return {"detail": f"用户 {row['username']} 已删除"}


# ===================================================================
# 精灵管理（不支持创建）
# ===================================================================


@router.get("/elfies")
async def list_elfies(
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin),
) -> list:
    """列出所有精灵。

    通过 ``LEFT JOIN users`` 获取 ``owner_username``。
    返回字段包含所有 registry 信息及外观属性（personality_style, height, build）。
    """
    _ = admin
    db_path: str = request.app.state.db_path
    with get_db(db_path) as conn:
        cursor = conn.execute("""
            SELECT e.id, e.elfie_id, e.name, e.owner_user_id, e.anatomy_type,
                   e.personality_style, e.height, e.build, e.created_at,
                   u.username AS owner_username
            FROM elfie_registry e
            LEFT JOIN users u ON e.owner_user_id = u.id
            ORDER BY e.id
        """)
        rows = cursor.fetchall()

    return [
        {
            "id": r["id"],
            "elfie_id": r["elfie_id"],
            "name": r["name"],
            "owner_user_id": r["owner_user_id"],
            "owner_username": r["owner_username"],
            "anatomy_type": r["anatomy_type"],
            "personality_style": r["personality_style"],
            "height": r["height"],
            "build": r["build"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.put("/elfies/{elfie_id}")
async def update_elfie(
    elfie_id: str,
    body: Dict[str, Any],
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """修改精灵信息。

    可修改字段: ``name``, ``owner_user_id``。
    **不可修改 ``anatomy_type``**（领养时确定，不可变）。
    """
    _ = admin
    db_path: str = request.app.state.db_path

    # 检查精灵存在性
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """SELECT id, elfie_id, name, owner_user_id, anatomy_type,
                      personality_style, height, build, created_at
               FROM elfie_registry WHERE elfie_id = ?""",
            (elfie_id,),
        )
        row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="精灵不存在")

    # 禁止修改 anatomy_type
    if "anatomy_type" in body:
        raise HTTPException(
            status_code=400,
            detail="不可修改 anatomy_type（领养时确定，不可变）",
        )

    # 构建动态 UPDATE
    updates: list[str] = []
    params: list[Any] = []

    name = body.get("name")
    if name is not None:
        name = str(name).strip()
        if not name:
            raise HTTPException(status_code=422, detail="名字不能为空")
        updates.append("name = ?")
        params.append(name)

    owner_user_id = body.get("owner_user_id")
    if owner_user_id is not None:
        # 验证目标 owner 存在
        with get_db(db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE id = ?",
                (owner_user_id,),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="目标用户不存在")
        updates.append("owner_user_id = ?")
        params.append(owner_user_id)

    if not updates:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")

    params.append(elfie_id)
    with get_db(db_path) as conn:
        conn.execute(
            f"UPDATE elfie_registry SET {', '.join(updates)} WHERE elfie_id = ?",
            params,
        )
        conn.commit()
        cursor = conn.execute(
            """SELECT id, elfie_id, name, owner_user_id, anatomy_type,
                      personality_style, height, build, created_at
               FROM elfie_registry WHERE elfie_id = ?""",
            (elfie_id,),
        )
        row = cursor.fetchone()

    return {
        "id": row["id"],
        "elfie_id": row["elfie_id"],
        "name": row["name"],
        "owner_user_id": row["owner_user_id"],
        "anatomy_type": row["anatomy_type"],
        "personality_style": row["personality_style"],
        "height": row["height"],
        "build": row["build"],
        "created_at": row["created_at"],
    }


@router.delete("/elfies/{elfie_id}")
async def delete_elfie(
    elfie_id: str,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """从 registry 删除精灵。

    OWNER 级别事务：仅从 ``elfie_registry`` 表删除记录，
    不删除精灵的配置目录 ``data/elfies/<id>/``。
    （配置目录保留以便日后恢复。）
    """
    _ = admin
    db_path: str = request.app.state.db_path

    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT id, name FROM elfie_registry WHERE elfie_id = ?",
            (elfie_id,),
        )
        row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="精灵不存在")

    with get_db(db_path) as conn:
        conn.execute(
            "DELETE FROM elfie_registry WHERE elfie_id = ?",
            (elfie_id,),
        )
        conn.commit()

    logger.info("Admin deleted elfie %s (%s)", elfie_id, row["name"])
    return {"detail": f"精灵 {row['name']} 已删除"}


# ===================================================================
# LLM 配置管理
# ===================================================================


@router.get("/config")
async def get_config(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """读取 ``runtime_config.json``。

    文件可能不存在（gitignored 且尚未创建），此时返回 ``{}``。
    解析失败（非法 JSON）同样返回 ``{}``。
    """
    _ = admin
    if not _RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        with open(_RUNTIME_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


@router.put("/config")
async def update_config(
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """写入 ``runtime_config.json``。

    操作步骤：
    1. 校验 JSON 必须包含 ``providers`` 字典结构
    2. 如果旧文件存在，备份为 ``runtime_config.json.bak``
    3. 写入新内容

    .. warning::
        修改配置可能影响所有精灵的 LLM 行为。
    """
    _ = admin
    # 校验
    if "providers" not in body or not isinstance(body["providers"], dict):
        raise HTTPException(
            status_code=400,
            detail="配置必须包含 providers 字典结构",
        )

    # 备份旧文件
    if _RUNTIME_CONFIG_PATH.exists():
        backup_path = _RUNTIME_CONFIG_PATH.with_suffix(".json.bak")
        shutil.copy2(str(_RUNTIME_CONFIG_PATH), str(backup_path))
        logger.info("Config backed up to %s", backup_path)

    # 确保 runtime/ 目录存在
    _RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 写入
    with open(_RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)

    logger.info("Runtime config updated by admin")
    return {"detail": "配置已更新"}
