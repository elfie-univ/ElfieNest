"""FastAPI 应用骨架 — 静态文件挂载、CORS、健康检查、login/logout/me 路由。

使用工厂函数 ``create_app`` 创建 FastAPI 实例。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional  # noqa: E402

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ai_runtime.storage.data_home import get_db_path as _get_db_path
from app.features.accounts import AccountsService
from app.features.adoption import AdoptionService
from app.features.bodies import BodiesService
from app.features.communication import CommunicationFacade
from app.features.configuration import (
    CapabilitiesService,
    FoodService,
    ProvidersService,
    SettingsService,
)
from app.features.elfies import ElfiesService
from app.features.nest_management import NestManagementService
from app.features.operations import OperationsFacade
from app.features.setup import SetupService
from app.infrastructure.persistence.store import (
    init_db,
    seed_initial_owner_if_env_set,
)
from app.interfaces.web.build_discovery import (
    WebBuildManifestMalformedError,
    WebBuildManifestMissingError,
    discover_web_build,
)
from app.orchestration.embodiment import BodyDeviceChannel, EmbodimentSessionService
from app.orchestration.message_delivery import MessageDeliveryFacade
from app.orchestration.observer import ObserverFacade
from app.orchestration.resident_admission import ResidentAdmissionService
from app.orchestration.setup_installation import SetupInstallationService
from infrastructure.communication import SameOriginMessagePublisher
from nest.godot_gateway.bundle import GODOT_WEB_DIR, godot_web_bundle_present

from .health_models import HealthResponse
from .page_routes import router as page_router
from .request_limits import AvatarUploadBodyLimitMiddleware
from .service_access import ServiceAccessPolicy, configure_service_access
from .v1.auth import verify_csrf_token
from .ws_gateway import AuthenticatedWSManager

logger = logging.getLogger("app.interfaces.api.app")


# ---------------------------------------------------------------------------
# CSRF 校验依赖
# ---------------------------------------------------------------------------


def verify_csrf_for_session(request: Request) -> None:
    """Check the normal session CSRF pair for mutating requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    session_token = request.cookies.get("session_token")
    csrf_token = request.headers.get("X-CSRF-Token")

    if not session_token or not csrf_token:
        raise HTTPException(status_code=403, detail="缺少 CSRF token")

    if not verify_csrf_token(session_token, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF token 无效")


def verify_csrf_for_setup(request: Request) -> None:
    """Check the temporary, local-only Setup CSRF pair before an Owner exists."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    setup_token = request.cookies.get("setup_token")
    csrf_token = request.headers.get("X-CSRF-Token")
    if not setup_token or not csrf_token:
        raise HTTPException(status_code=403, detail="缺少 Setup CSRF token")
    if not verify_csrf_token(setup_token, csrf_token):
        raise HTTPException(status_code=403, detail="Setup CSRF token 无效")


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------


def create_http_application(
    accounts: AccountsService,
    settings: SettingsService,
    nest_management: NestManagementService,
    elfies: ElfiesService,
    providers: ProvidersService,
    food: FoodService,
    capabilities: CapabilitiesService,
    operations: OperationsFacade,
    communication: CommunicationFacade,
    message_delivery: MessageDeliveryFacade,
    communication_realtime: SameOriginMessagePublisher,
    observer: ObserverFacade,
    adoption: AdoptionService,
    resident_admission: ResidentAdmissionService,
    setup: SetupService,
    setup_installation: SetupInstallationService,
    bodies: BodiesService,
    embodiment: EmbodimentSessionService,
    body_device_channel: BodyDeviceChannel,
    engine: Any = None,
    db_path: Optional[str] = None,
    ws_port: int = 8766,
    http_port: int = 8000,
    service_mode: str = "loopback",
    web_build_dir: Optional[Path] = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        engine: An optional ``ElfieNestEngine`` instance.  When provided, the
            health endpoint reports ``engine_ready: true`` and routes that need
            engine access (adoption, config, etc.) become functional.
        db_path: Path to the SQLite database file.
        ws_port: Port for the authenticated WebSocket gateway (default 8766).
        http_port: Port serving the browser console (default 8000).

    Returns:
        A fully configured :class:`FastAPI` instance.
    """
    if db_path is None:
        db_path = str(_get_db_path())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(db_path)
        setup_installation.recover()
        seed_initial_owner_if_env_set(db_path)
        # 创建鉴权 WS 网关（独立端口，不与 Godot 8765 冲突）
        ws_manager = AuthenticatedWSManager(
            accounts=accounts,
            message_delivery=message_delivery,
            port=ws_port,
            http_port=http_port,
        )
        if engine is not None:
            engine.session.owner_broadcaster = ws_manager
        ws_manager.start()
        app.state.ws_manager = ws_manager

        logger.info("App startup complete (db=%s, ws=%d)", db_path, ws_manager.port)
        yield

        ws_manager.stop()
        logger.info("App shutdown complete")

    app = FastAPI(title="ElfieNest Management Dashboard", lifespan=lifespan)

    # 将 db_path 与 engine 存入 app.state 供依赖注入使用
    app.state.accounts = accounts
    app.state.settings = settings
    app.state.nest_management = nest_management
    app.state.elfies = elfies
    app.state.providers = providers
    app.state.food = food
    app.state.capabilities = capabilities
    app.state.operations = operations
    app.state.communication = communication
    app.state.message_delivery = message_delivery
    app.state.communication_realtime = communication_realtime
    app.state.observer = observer
    app.state.adoption = adoption
    app.state.resident_admission = resident_admission
    app.state.setup = setup
    app.state.setup_installation = setup_installation
    app.state.bodies = bodies
    app.state.embodiment = embodiment
    app.state.body_device_channel = body_device_channel
    app.state.db_path = db_path
    app.state.engine = engine
    app.state.ws_port = ws_port
    configured_web_build_dir = os.environ.get("ELFIENEST_WEB_BUILD_DIR")
    build_dir = web_build_dir or (
        Path(configured_web_build_dir)
        if configured_web_build_dir
        else Path(__file__).resolve().parents[3] / "build" / "web"
    )
    try:
        app.state.web_build = discover_web_build(build_dir)
        app.state.web_build_error = None
    except (WebBuildManifestMissingError, WebBuildManifestMalformedError) as error:
        app.state.web_build = None
        app.state.web_build_error = str(error)
    app.add_middleware(AvatarUploadBodyLimitMiddleware)

    service_access = ServiceAccessPolicy.create(service_mode, http_port)
    configure_service_access(app, service_access)

    # -------------------------------------------------------------------
    # CORS — 允许 127.0.0.1 和 localhost
    # -------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(service_access.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount(
        "/runtime/godot",
        StaticFiles(directory=str(GODOT_WEB_DIR), check_dir=False),
        name="godot-runtime",
    )

    # -------------------------------------------------------------------
    # 全局异常处理 — 未捕获异常返回 500 结构化 JSON 不泄露 traceback
    # -------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
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
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            csrf_exempt = path == "/api/v1/auth/login"
            if not csrf_exempt:
                try:
                    if path.startswith("/api/v1/setup/draft/"):
                        verify_csrf_for_setup(request)
                    elif path == "/api/v1/setup/installation" and request.cookies.get(
                        "setup_token"
                    ):
                        verify_csrf_for_setup(request)
                    else:
                        verify_csrf_for_session(request)
                except HTTPException as exc:
                    return JSONResponse(
                        status_code=exc.status_code,
                        content={"detail": exc.detail},
                    )
        return await call_next(request)

    # -------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """健康检查"""
        return HealthResponse(
            status="ok",
            engine_ready=engine is not None,
            godot_web_ready=godot_web_bundle_present(),
            godot_runtime_ready=bool(
                engine is not None and engine.world_runtime.runtime_ready
            ),
        )

    # -------------------------------------------------------------------
    # Setup Wizard 路由（首启向导 — 在 owner 路由之前注册）
    # -------------------------------------------------------------------
    from .v1.admin.food_packages import (
        router as food_packages_router,  # noqa: PLC0415
    )
    from .v1.admin.model_providers import (
        router as model_providers_router,  # noqa: PLC0415
    )
    from .v1.admin.nest import router as nest_management_router  # noqa: PLC0415
    from .v1.admin.runtime import router as runtime_router  # noqa: PLC0415
    from .v1.admin.settings import router as settings_router  # noqa: PLC0415
    from .v1.admin.settings.capabilities import (
        router as capabilities_router,  # noqa: PLC0415
    )
    from .v1.admin.users import router as admin_users_router  # noqa: PLC0415
    from .v1.auth.routes import router as auth_router  # noqa: PLC0415
    from .v1.elfies.bodies import router as bodies_router  # noqa: PLC0415
    from .v1.elfies.food_policy import (
        router as elfie_food_policy_router,  # noqa: PLC0415
    )
    from .v1.me import router as me_router  # noqa: PLC0415
    from .v1.me.adoption import router as adoption_router  # noqa: PLC0415
    from .v1.me.conversations import (
        router as conversations_router,  # noqa: PLC0415
    )
    from .v1.observer import router as observer_router  # noqa: PLC0415
    from .v1.realtime.bodies import router as body_realtime_router  # noqa: PLC0415
    from .v1.realtime_chat_routes import (
        router as realtime_chat_router,  # noqa: PLC0415
    )
    from .v1.setup import router as setup_router  # noqa: PLC0415

    app.include_router(auth_router)
    app.include_router(settings_router)
    app.include_router(nest_management_router)
    app.include_router(model_providers_router)
    app.include_router(food_packages_router)
    app.include_router(elfie_food_policy_router)
    app.include_router(bodies_router)
    app.include_router(capabilities_router)
    app.include_router(runtime_router)
    app.include_router(me_router)
    app.include_router(adoption_router)
    app.include_router(conversations_router)
    app.include_router(observer_router)
    app.include_router(realtime_chat_router)
    app.include_router(body_realtime_router)
    app.include_router(admin_users_router)
    app.include_router(setup_router)
    app.include_router(page_router)
    from .v1.client_routes import router as v1_client_router  # noqa: PLC0415

    app.include_router(v1_client_router)

    # -------------------------------------------------------------------
    # Owner REST API 路由
    # -------------------------------------------------------------------
    from .owner_elfie_routes import router as owner_elfie_router  # noqa: PLC0415

    app.include_router(owner_elfie_router)
    return app
