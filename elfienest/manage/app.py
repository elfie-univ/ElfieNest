"""FastAPI 应用骨架 — 静态文件挂载、CORS、健康检查、login/logout/me 路由。

使用工厂函数 ``create_app`` 创建 FastAPI 实例。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    create_session,
    delete_session,
    generate_csrf_token,
    rate_limiter,
    verify_csrf_token,
    verify_password,
    verify_session,
)
from .store import get_db, init_db, seed_admin

logger = logging.getLogger("elfienest.manage.app")

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
    db_path: str = "data/nest.db",
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        engine: An optional ``ElfieNestEngine`` instance.  When provided, the
            health endpoint reports ``engine_ready: true`` and routes that need
            engine access (adoption, config, etc.) become functional.
        db_path: Path to the SQLite database file.

    Returns:
        A fully configured :class:`FastAPI` instance.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(db_path)
        seed_admin(db_path)
        logger.info("App startup complete (db=%s)", db_path)
        yield

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
    # 静态文件挂载 — templates/ 目录
    # -------------------------------------------------------------------
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(templates_dir)), name="static")

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
            if not path.startswith("/api/auth/login"):
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
        """根路径重定向到登录页"""
        return RedirectResponse(url="/static/login.html", status_code=302)

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
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""

        if not username or not password:
            raise HTTPException(status_code=422, detail="用户名和密码不能为空")

        client_ip = request.client.host if request.client else "unknown"

        # 速率限制
        if rate_limiter.is_limited(client_ip, username):
            raise HTTPException(
                status_code=429,
                detail="登录尝试过于频繁，请稍后再试",
            )

        # 验证凭据
        db = request.app.state.db_path
        with get_db(db) as conn:
            cursor = conn.execute(
                "SELECT id, username, password_hash, role FROM users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()

        if row is None or not verify_password(password, row["password_hash"]):
            rate_limiter.record_failure(client_ip, username)
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 登录成功 — 清零速率限制，创建 session
        rate_limiter.clear(client_ip, username)
        session_token = create_session(row["id"], db)
        csrf_token = generate_csrf_token(session_token)

        user_data = {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
        }

        resp = JSONResponse(content={"user": user_data, "csrf_token": csrf_token})
        resp.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            samesite="lax",
            max_age=7 * 86400,
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
    async def me(user: Dict[str, Any] = Depends(get_current_user)):  # noqa: B008
        """返回当前登录用户信息。"""
        return user

    # -------------------------------------------------------------------
    # Routers
    # -------------------------------------------------------------------
    try:
        from .admin_routes import router as admin_router  # noqa: PLC0415
        app.include_router(admin_router)
    except ImportError:
        pass
    try:
        from .user_routes import router as user_router  # noqa: PLC0415
        app.include_router(user_router)
    except ImportError:
        pass

    return app
