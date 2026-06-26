"""Auth 核心 — PBKDF2 密码哈希 + session token + 鉴权中间件 + CSRF + 速率限制。

重用了 store.py 中的 hash_password / verify_password 实现。
FastAPI 依赖（get_current_user / require_admin）仅在对应的函数中按需导入，
不在模块顶层强依赖 FastAPI。
"""

from __future__ import annotations

import hmac
import logging
import secrets
import time
from typing import Any, Dict, List, Optional

from elfienest.persistence.store import get_db

# 重导出 store.py 中的哈希函数，便于 auth 层统一 import
from elfienest.persistence.store import hash_password as hash_password  # noqa: F401
from elfienest.persistence.store import verify_password as verify_password  # noqa: F401
from runtime.data_home import get_db_path as _get_db_path

logger = logging.getLogger("elfienest.accounts.auth")

# ---------------------------------------------------------------------------
# CSRF 保护 — HMAC-based，绑定到 session
# ---------------------------------------------------------------------------

_CSRF_SECRET: str = secrets.token_hex(32)
"""服务端 CSRF HMAC 密钥，进程生命周期内保持不变。"""

_CSRF_DIGEST: str = "sha256"


def generate_csrf_token(session_token: str) -> str:
    """生成绑定到 *session_token* 的 CSRF token。

    HMAC-SHA256(session_token, server_secret)，输出 hex 字符串。
    前端在后续 POST/PUT/DELETE 请求中通过 ``X-CSRF-Token`` 头部携带此值。
    """
    return hmac.new(
        _CSRF_SECRET.encode("utf-8"),
        session_token.encode("utf-8"),
        _CSRF_DIGEST,
    ).hexdigest()


def verify_csrf_token(session_token: str, csrf_token: str) -> bool:
    """验证 *csrf_token* 是否与 *session_token* 匹配。

    使用 **hmac.compare_digest** 防止时序攻击。
    """
    expected = generate_csrf_token(session_token)
    return hmac.compare_digest(expected, csrf_token)


# ---------------------------------------------------------------------------
# Session 管理
# ---------------------------------------------------------------------------

_session_config: Dict[str, int] = {"ttl_seconds": 7 * 86_400}


def get_session_ttl_seconds(db_path: Optional[str] = None) -> int:
    """获取 session TTL（秒），从 system.security 读取并缓存。

    Args:
        db_path: 数据库路径（用于可能的扩展）

    Returns:
        TTL 秒数
    """
    from runtime.config import LLMRuntimeConfig  # noqa: PLC0415

    config = LLMRuntimeConfig()
    ttl_days = config.system.get("security", {}).get("session_ttl_days", 7)
    ttl_seconds = ttl_days * 86400

    # 更新缓存
    _session_config["ttl_seconds"] = ttl_seconds

    return ttl_seconds


def invalidate_session_cache() -> None:
    """清除 session TTL 缓存（配置更新后调用）。

    下次调用 ``get_session_ttl_seconds`` 会重新读取配置。
    """
    # 缓存下次调用时自动更新，此函数为外部触发接口
    pass


def create_session(user_id: int, db_path: str = None) -> str:
    """为 *user_id* 创建新 session，返回 64 字符 hex token。

    生成 32 字节随机 token（secrets.token_hex），插入 ``sessions`` 表，
    ``expires_at`` 设为当前时间 + ``system.security.session_ttl_days`` 天。
    """
    if db_path is None:
        db_path = str(_get_db_path())
    token = secrets.token_hex(32)
    expires_at = time.time() + get_session_ttl_seconds(db_path)

    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        conn.commit()

    logger.debug("Session created for user_id=%d", user_id)
    return token


def verify_session(token: str, db_path: str = None) -> Optional[Dict[str, Any]]:
    """验证 *token* 对应的 session 是否有效且未过期。

    检查 sessions 表 + JOIN users 表获取用户信息。
    自动过滤已过期 session（expires_at > 当前时间戳）。

    Returns:
        ``{"id": ..., "username": ..., "role": ...}`` 或 ``None``（无效/过期）。
    """
    now = time.time()

    with get_db(db_path) as conn:
        cursor = conn.execute(
            """SELECT u.id, u.username, u.role
               FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.token = ? AND s.expires_at > ?""",
            (token, now),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def delete_session(token: str, db_path: str = None) -> None:
    """从 ``sessions`` 表中删除 *token* 对应的 session。"""
    if db_path is None:
        db_path = str(_get_db_path())
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()

    logger.debug("Session deleted for token=%s...", token[:16])


# ---------------------------------------------------------------------------
# FastAPI 鉴权依赖（函数体内部按需导入 FastAPI 类型）
# ---------------------------------------------------------------------------


def get_current_user(request=None):
    """FastAPI ``Depends`` 用鉴权中间件。

    从 cookie ``session_token`` 读取 token，调 ``verify_session`` 验证。
    无效/过期 token 触发 HTTP 401。

    Usage::

        @router.get("/protected")
        def protected(user: dict = Depends(get_current_user)):
            return user
    """
    from fastapi import HTTPException  # noqa: PLC0415
    from fastapi import Request as FastAPIRequest

    if request is None or not isinstance(request, FastAPIRequest):
        raise HTTPException(status_code=401, detail="未提供请求对象")

    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="未登录，缺少会话 token")

    user = verify_session(token)
    if user is None:
        raise HTTPException(status_code=401, detail="会话无效或已过期")

    return user


def require_admin(user=None):
    """FastAPI ``Depends`` 管理员权限校验。

    必须在 ``get_current_user`` 之后链式使用：:

        @router.get("/admin-only")
        def admin_only(user: dict = Depends(require_admin)):
            ...
    """
    from fastapi import HTTPException  # noqa: PLC0415

    if user is None:
        raise HTTPException(status_code=401, detail="未登录")

    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    return user


# ---------------------------------------------------------------------------
# 登录速率限制
# ---------------------------------------------------------------------------


class RateLimiter:
    """内存登录速率限制器。

    按 ``{ip}:{username}`` 记录失败时间戳。在 **window_seconds** 内
    超过 **max_attempts** 次失败返回 ``True``（触发 429）。
    成功登录请调用 ``clear()`` 清零对应 key。

    Usage::

        limiter = RateLimiter()

        if limiter.is_limited(ip, username):
            raise HTTPException(429)

        if not verify_password(...):
            limiter.record_failure(ip, username)
            raise HTTPException(401)
        else:
            limiter.clear(ip, username)
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._records: Dict[str, List[float]] = {}

    def _key(self, ip: str, username: str) -> str:
        return f"{ip}:{username}"

    def is_limited(self, ip: str, username: str) -> bool:
        """检查 *ip+username* 组合是否达到速率限制。"""
        key = self._key(ip, username)
        now = time.time()
        timestamps = self._records.get(key, [])
        cutoff = now - self._window_seconds
        # 只保留窗口内的时间戳
        timestamps = [t for t in timestamps if t > cutoff]
        self._records[key] = timestamps
        return len(timestamps) >= self._max_attempts

    def record_failure(self, ip: str, username: str) -> None:
        """记录一次登录失败。"""
        key = self._key(ip, username)
        if key not in self._records:
            self._records[key] = []
        self._records[key].append(time.time())

    def clear(self, ip: str, username: str) -> None:
        """登录成功后清零 *ip+username* 的失败记录。"""
        key = self._key(ip, username)
        self._records.pop(key, None)


# 全局速率限制器缓存（按配置参数缓存）
_rate_limiter_cache: Dict[str, RateLimiter] = {}


def get_rate_limiter(db_path: Optional[str] = None) -> RateLimiter:
    """获取 RateLimiter 实例（按配置缓存）。

    Args:
        db_path: 数据库路径（用于缓存键，保留作扩展用）

    Returns:
        RateLimiter 实例
    """
    from runtime.config import LLMRuntimeConfig  # noqa: PLC0415

    config = LLMRuntimeConfig()
    security = config.system.get("security", {})
    rate_config = security.get("rate_limit", {})

    max_attempts = rate_config.get("max_attempts", 5)
    window_seconds = rate_config.get("window_seconds", 300)

    # 使用配置参数作为缓存键
    cache_key = f"{max_attempts}:{window_seconds}"

    if cache_key not in _rate_limiter_cache:
        _rate_limiter_cache[cache_key] = RateLimiter(
            max_attempts=max_attempts, window_seconds=window_seconds
        )

    return _rate_limiter_cache[cache_key]


def invalidate_rate_limiter_cache() -> None:
    """清除 RateLimiter 缓存（配置更新后调用）。"""
    _rate_limiter_cache.clear()
