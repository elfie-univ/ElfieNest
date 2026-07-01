"""FastAPI 应用骨架 — 静态文件挂载、CORS、健康检查、login/logout/me 路由。

使用工厂函数 ``create_app`` 创建 FastAPI 实例。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import (
    Any,
    Dict,
    Optional,  # noqa: E402
)

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field  # noqa: E402

from elfienest.accounts.auth import (
    create_session,
    delete_session,
    generate_csrf_token,
    get_rate_limiter,
    get_session_ttl_seconds,
    hash_password,
    verify_csrf_token,
    verify_password,
    verify_session,
)
from elfienest.persistence.store import (
    get_db,
    init_db,
    migrate_db_if_needed,
    seed_initial_admin_if_env_set,
)
from elfienest.ui import STATIC_DIR
from runtime.storage.data_home import get_db_path as _get_db_path

from .ws_gateway import AuthenticatedWSManager

logger = logging.getLogger("elfienest.api.app")


# ---------------------------------------------------------------------------
# Pydantic 模型（profile / password 请求体）
# ---------------------------------------------------------------------------


class ProfileUpdate(BaseModel):
    nickname: Optional[str] = Field(None, max_length=32)
    avatar_color: Optional[int] = Field(None, ge=0, le=7)
    avatar_kind: Optional[str] = Field(None, pattern="^(initials|emoji)$")


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)

# ---------------------------------------------------------------------------
# CSRF 校验依赖
# ---------------------------------------------------------------------------


def verify_csrf_for_session(request: Request) -> None:
    """检查 POST/PUT/DELETE 请求的 X-CSRF-Token header。

    从 cookie 取 session_token，从 header 取 csrf_token，
    调用 ``verify_csrf_token`` 校验。
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    session_token = request.cookies.get("session_token")
    csrf_token = request.headers.get("X-CSRF-Token")

    if not session_token or not csrf_token:
        raise HTTPException(status_code=403, detail="缺少 CSRF token")

    if not verify_csrf_token(session_token, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF token 无效")


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------


def create_app(
    engine: Any = None,
    db_path: Optional[str] = None,
    ws_port: int = 8766,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        engine: An optional ``ElfieNestEngine`` instance.  When provided, the
            health endpoint reports ``engine_ready: true`` and routes that need
            engine access (adoption, config, etc.) become functional.
        db_path: Path to the SQLite database file.
        ws_port: Port for the authenticated WebSocket gateway (default 8766).

    Returns:
        A fully configured :class:`FastAPI` instance.
    """
    if db_path is None:
        db_path = str(_get_db_path())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(db_path)
        migrate_db_if_needed(db_path)
        seed_initial_admin_if_env_set(db_path)

        # 创建鉴权 WS 网关（独立端口，不与 Godot 8765 冲突）
        ws_manager = AuthenticatedWSManager(port=ws_port, db_path=db_path)
        if engine is not None:
            engine.ws_manager = ws_manager
            ws_manager.coordinator = engine.coordinator
        ws_manager.start()
        app.state.ws_manager = ws_manager

        logger.info("App startup complete (db=%s, ws=%d)", db_path, ws_manager.port)
        yield

        ws_manager.stop()
        logger.info("App shutdown complete")

    app = FastAPI(title="ElfieNest Management Dashboard", lifespan=lifespan)

    # 将 db_path 与 engine 存入 app.state 供依赖注入使用
    app.state.db_path = db_path
    app.state.engine = engine

    # -------------------------------------------------------------------
    # CORS — 允许 127.0.0.1 和 localhost
    # -------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------------------------
    async def static_index_redirect() -> RedirectResponse:
        return RedirectResponse("/", status_code=308)

    app.add_api_route(
        "/static/index.html",
        static_index_redirect,
        methods=["GET"],
        include_in_schema=False,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # -------------------------------------------------------------------
    # 全局异常处理 — 未捕获异常返回 500 结构化 JSON 不泄露 traceback
    # -------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )

    # -------------------------------------------------------------------
    # CSRF 中间件（login 端点豁免）
    # -------------------------------------------------------------------
    @app.middleware("http")
    async def csrf_middleware(request: Request, call_next):
        if request.method in ("POST", "PUT", "DELETE"):
            path = request.url.path
            if path != "/api/auth/login" and path != "/api/auth/setup":
                try:
                    verify_csrf_for_session(request)
                except HTTPException as exc:
                    return JSONResponse(
                        status_code=exc.status_code,
                        content={"detail": exc.detail},
                    )
        return await call_next(request)

    # -------------------------------------------------------------------
    # 本地 get_current_user 依赖（使用 app.state.db_path）
    # -------------------------------------------------------------------
    def get_current_user(request: Request) -> Dict[str, Any]:
        """从 session_token cookie 获取当前用户，使用 app 配置的 db_path。"""
        token = request.cookies.get("session_token")
        if not token:
            raise HTTPException(status_code=401, detail="未登录，缺少会话 token")
        db = request.app.state.db_path
        user = verify_session(token, db)
        if user is None:
            raise HTTPException(status_code=401, detail="会话无效或已过期")
        return user

    # -------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------

    @app.get("/")
    async def root_redirect():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/api/health")
    async def health():
        """健康检查"""
        return {"status": "ok", "engine_ready": engine is not None}

    @app.post("/api/auth/login")
    async def login(request: Request):
        """登录：校验身份 → 创建 session → 设置 cookie → 返回 user + CSRF token。

        请求体为 form-data（username, password）。login 端点豁免 CSRF 校验。
        """
        body = await request.form()
        username_raw = body.get("username")
        password_raw = body.get("password")
        username = (username_raw if isinstance(username_raw, str) else "").strip()
        password = password_raw if isinstance(password_raw, str) else ""

        if not username or not password:
            raise HTTPException(status_code=422, detail="用户名和密码不能为空")

        client_ip = request.client.host if request.client else "unknown"

        # 速率限制（从配置动态读取）
        db = request.app.state.db_path
        limiter = get_rate_limiter(db)
        if limiter.is_limited(client_ip, username):
            raise HTTPException(
                status_code=429,
                detail="登录尝试过于频繁，请稍后再试",
            )

        # 验证凭据
        with get_db(db) as conn:
            cursor = conn.execute(
                "SELECT id, username, password_hash, role FROM users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()

        if row is None or not verify_password(password, row["password_hash"]):
            limiter.record_failure(client_ip, username)
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 登录成功 — 清零速率限制，创建 session
        limiter.clear(client_ip, username)
        session_token = create_session(row["id"], db)
        csrf_token = generate_csrf_token(session_token)

        user_data = {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
        }

        resp = JSONResponse(content={
            "user": user_data,
            "csrf_token": csrf_token,
            "session_token": session_token,
        })
        resp.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            samesite="lax",
            max_age=get_session_ttl_seconds(db),
        )
        resp.headers["X-CSRF-Token"] = csrf_token
        return resp

    @app.post("/api/auth/logout")
    async def logout(
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ):
        """登出：删除 session + 清除 cookie。需要 CSRF token。"""
        _ = user  # 确保已登录
        token = request.cookies.get("session_token", "")
        if token:
            delete_session(token, request.app.state.db_path)
        resp = JSONResponse(content={"detail": "已登出"})
        resp.delete_cookie(key="session_token")
        return resp

    @app.get("/api/auth/me")
    async def me(
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> Dict[str, Any]:
        """返回当前登录用户完整信息（含 CSRF token, profile, elfie_count）。"""
        db_path = request.app.state.db_path
        with get_db(db_path) as conn:
            cursor = conn.execute(
                "SELECT id, username, role, nickname, avatar_color, avatar_kind, "
                "created_at FROM users WHERE id = ?",
                (user["id"],),
            )
            row = cursor.fetchone()

            cursor = conn.execute(
                "SELECT COUNT(*) FROM elfie_registry WHERE owner_user_id = ?",
                (user["id"],),
            )
            elfie_count = cursor.fetchone()[0]

        session_token = request.cookies.get("session_token", "")
        csrf_token = (
            generate_csrf_token(session_token) if session_token else ""
        )

        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "nickname": row["nickname"],
            "avatar_color": row["avatar_color"],
            "avatar_kind": row["avatar_kind"],
            "created_at": row["created_at"],
            "elfie_count": elfie_count,
            "csrf_token": csrf_token,
            "session_token": session_token,
        }

    # -------------------------------------------------------------------
    # Profile routes (GET/PUT /api/auth/me/profile)
    # -------------------------------------------------------------------

    @app.get("/api/auth/me/profile")
    async def get_profile(
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> Dict[str, Any]:
        """返回当前用户 profile 子集（username, nickname, avatar_color, avatar_kind）。"""
        db_path = request.app.state.db_path
        with get_db(db_path) as conn:
            cursor = conn.execute(
                "SELECT username, nickname, avatar_color, avatar_kind "
                "FROM users WHERE id = ?",
                (user["id"],),
            )
            row = cursor.fetchone()

        return {
            "username": row["username"],
            "nickname": row["nickname"],
            "avatar_color": row["avatar_color"],
            "avatar_kind": row["avatar_kind"],
        }

    @app.put("/api/auth/me/profile")
    async def update_profile(
        body: ProfileUpdate,
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> Dict[str, Any]:
        """更新当前用户 profile（nickname, avatar_color, avatar_kind）。"""
        db_path = request.app.state.db_path

        updates: list[str] = []
        params: list[Any] = []

        if body.nickname is not None:
            updates.append("nickname = ?")
            params.append(body.nickname or None)

        if body.avatar_color is not None:
            updates.append("avatar_color = ?")
            params.append(body.avatar_color)

        if body.avatar_kind is not None:
            updates.append("avatar_kind = ?")
            params.append(body.avatar_kind)

        if not updates:
            raise HTTPException(status_code=400, detail="没有提供要更新的字段")

        params.append(user["id"])

        with get_db(db_path) as conn:
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT username, nickname, avatar_color, avatar_kind "
                "FROM users WHERE id = ?",
                (user["id"],),
            )
            row = cursor.fetchone()

        return {
            "username": row["username"],
            "nickname": row["nickname"],
            "avatar_color": row["avatar_color"],
            "avatar_kind": row["avatar_kind"],
        }

    @app.post("/api/auth/me/password")
    async def change_password(
        body: PasswordChange,
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> Dict[str, Any]:
        """修改当前用户密码。需要旧密码校验。"""
        db_path = request.app.state.db_path

        with get_db(db_path) as conn:
            cursor = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (user["id"],),
            )
            row = cursor.fetchone()

        if not verify_password(body.old_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="旧密码错误")

        if body.old_password == body.new_password:
            raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

        new_hash = hash_password(body.new_password)
        with get_db(db_path) as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, user["id"]),
            )
            conn.commit()

        return {"detail": "密码已更新"}

    # -------------------------------------------------------------------
    # Setup Wizard 路由（首启向导 — 在 admin 路由之前注册）
    # -------------------------------------------------------------------
    from .setup_routes import router as setup_router  # noqa: PLC0415

    app.include_router(setup_router)

    # -------------------------------------------------------------------
    # System Settings 路由
    # -------------------------------------------------------------------
    from .system_routes import router as system_router  # noqa: PLC0415

    app.include_router(system_router)

    # -------------------------------------------------------------------
    # Admin REST API 路由
    # -------------------------------------------------------------------
    from .admin_routes import router as admin_router  # noqa: PLC0415
    from .nest_routes import router as nest_router  # noqa: PLC0415
    from .nest_routes import user_router as user_nest_router  # noqa: PLC0415

    app.include_router(admin_router)
    app.include_router(nest_router)
    app.include_router(user_nest_router)
    from .user_routes import router as user_router  # noqa: PLC0415

    app.include_router(user_router)

    # -------------------------------------------------------------------
    # LLM Config 路由 (Provider/Model/Route 管理)
    # -------------------------------------------------------------------
    from .provider_routes import router as provider_router  # noqa: PLC0415

    app.include_router(provider_router)
    from .model_admin_routes import router as model_admin_router  # noqa: PLC0415

    app.include_router(model_admin_router)
    from .route_routes import router as route_router  # noqa: PLC0415

    app.include_router(route_router)
    from .runtime_routes import router as runtime_router  # noqa: PLC0415

    app.include_router(runtime_router)

    return app
