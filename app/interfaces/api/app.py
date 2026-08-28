"""FastAPI 应用骨架 — 静态文件挂载、CORS、健康检查、login/logout/me 路由。

使用工厂函数 ``create_app`` 创建 FastAPI 实例。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import (
    AsyncContextManager,
    Callable,
    Final,
    Mapping,
    Protocol,
)  # noqa: E402

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from app.features.accounts import AccountsService
from app.features.adoption import AdoptionService
from app.features.bodies import BodiesService
from app.features.communication import (
    CommunicationFacade,
    DiscordAccountsService,
    TelegramAccountsService,
)
from app.features.configuration import (
    CapabilitiesService,
    FoodService,
    ProviderAvailabilityPort,
    ProvidersService,
    SettingsService,
)
from app.features.elfies import ElfiesService
from app.features.nest_management import NestManagementService
from app.features.operations import OperationsFacade
from app.features.setup import SetupService
from app.interfaces.web.build_discovery import WebBuild
from app.orchestration.embodiment import BodyDeviceChannel, EmbodimentSessionService
from app.orchestration.message_delivery import MessageDeliveryFacade
from app.orchestration.observer import ObserverFacade, SessionLogoutWorkflow
from app.orchestration.resident_admission import ResidentAdmissionService
from app.orchestration.setup_installation import SetupInstallationService

from .errors import (
    ValidationIssue,
    api_error_response,
    error_message,
    http_error_code,
)
from .health_models import HealthResponse
from .page_routes import router as page_router
from .request_limits import AvatarUploadBodyLimitMiddleware
from .runtime_capability import RuntimeCapabilityGate
from .service_access import ServiceAccessPolicy, configure_service_access
from .v1.auth import verify_csrf_token

logger = logging.getLogger("app.interfaces.api.app")

_SETUP_INSTALLATION_MUTATION_PATHS: Final = frozenset(
    {
        "/api/v1/setup/installation",
        "/api/v1/setup/installation/cancel",
    }
)


class CommunicationRealtimePort(Protocol):
    """Same-origin connection surface consumed by the chat Interface."""

    async def connect(self, user_id: int, websocket: WebSocket) -> None: ...

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None: ...


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


def _log_csrf_rejection(request: Request, error: HTTPException) -> None:
    """Record safe presence/origin facts without ever logging credential values."""
    cookies = request.cookies
    logger.warning(
        "CSRF rejected method=%s path=%s detail=%s "
        "setup_cookie_present=%s setup_cookie_nonempty=%s "
        "session_cookie_present=%s csrf_header_present=%s "
        "request_host=%s origin=%s",
        request.method,
        request.url.path,
        error_message(error.detail),
        "setup_token" in cookies,
        bool(cookies.get("setup_token")),
        "session_token" in cookies,
        bool(request.headers.get("X-CSRF-Token")),
        request.url.hostname or "<none>",
        request.headers.get("origin", "<none>"),
    )


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------


def create_http_application(
    accounts: AccountsService,
    settings: SettingsService,
    nest_management: NestManagementService,
    elfies: ElfiesService,
    providers: ProvidersService,
    availability: ProviderAvailabilityPort,
    food: FoodService,
    capabilities: CapabilitiesService,
    operations: OperationsFacade,
    communication: CommunicationFacade,
    message_delivery: MessageDeliveryFacade,
    communication_realtime: CommunicationRealtimePort,
    telegram_accounts: TelegramAccountsService,
    discord_accounts: DiscordAccountsService,
    observer: ObserverFacade,
    session_logout: SessionLogoutWorkflow,
    adoption: AdoptionService,
    resident_admission: ResidentAdmissionService,
    setup: SetupService,
    setup_installation: SetupInstallationService,
    bodies: BodiesService,
    embodiment: EmbodimentSessionService,
    body_device_channel: BodyDeviceChannel,
    lifespan: Callable[[FastAPI], AsyncContextManager[None]],
    engine_ready: Callable[[], bool],
    godot_web_ready: Callable[[], bool],
    godot_runtime_ready: Callable[[], bool],
    godot_web_dir: Path,
    service_access: ServiceAccessPolicy,
    web_build: WebBuild | None,
    web_build_error: str | None,
    runtime_capability_gate: RuntimeCapabilityGate | None = None,
    runtime_projection: Callable[[], Mapping[str, object]] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
    Returns:
        A fully configured :class:`FastAPI` instance.
    """

    app = FastAPI(title="ElfieNest Management Dashboard", lifespan=lifespan)

    # Store only injected public application boundaries for request dependencies.
    app.state.accounts = accounts
    app.state.settings = settings
    app.state.nest_management = nest_management
    app.state.elfies = elfies
    app.state.providers = providers
    app.state.provider_availability = availability
    app.state.food = food
    app.state.capabilities = capabilities
    app.state.operations = operations
    app.state.communication = communication
    app.state.message_delivery = message_delivery
    app.state.communication_realtime = communication_realtime
    app.state.telegram_accounts = telegram_accounts
    app.state.discord_accounts = discord_accounts
    app.state.observer = observer
    app.state.session_logout = session_logout
    app.state.adoption = adoption
    app.state.resident_admission = resident_admission
    app.state.setup = setup
    app.state.setup_installation = setup_installation
    app.state.bodies = bodies
    app.state.embodiment = embodiment
    app.state.body_device_channel = body_device_channel
    app.state.web_build = web_build
    app.state.web_build_error = web_build_error
    app.state.runtime_capability_gate = runtime_capability_gate
    app.state.runtime_projection = runtime_projection
    app.add_middleware(AvatarUploadBodyLimitMiddleware)

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
        StaticFiles(directory=str(godot_web_dir), check_dir=False),
        name="godot-runtime",
    )

    # -------------------------------------------------------------------
    # 全局异常处理 — 未捕获异常返回 500 结构化 JSON 不泄露 traceback
    # -------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        route = request.scope.get("route")
        route_template = getattr(route, "path", "<unmatched>")
        logger.exception("Unhandled exception: %s %s", request.method, route_template)
        return api_error_response(500, "internal_error", "Internal Server Error")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        return api_error_response(
            exc.status_code,
            http_error_code(exc.status_code),
            error_message(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        issues = tuple(
            ValidationIssue(
                location=tuple(str(part) for part in error.get("loc", ())),
                message=str(error.get("msg", "字段无效")),
                kind=str(error.get("type", "validation_error")),
            )
            for error in exc.errors()
        )
        return api_error_response(
            422,
            "invalid_request",
            "请求字段无效",
            issues=issues,
        )

    # -------------------------------------------------------------------
    # CSRF 中间件（匿名认证端点豁免）
    # -------------------------------------------------------------------
    @app.middleware("http")
    async def csrf_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            csrf_exempt = path in {
                "/api/v1/auth/login",
                "/api/v1/auth/register",
            }
            if not csrf_exempt:
                try:
                    if path.startswith("/api/v1/setup/draft/"):
                        verify_csrf_for_setup(request)
                    elif (
                        path in _SETUP_INSTALLATION_MUTATION_PATHS
                        and request.cookies.get("setup_token")
                    ):
                        verify_csrf_for_setup(request)
                    else:
                        verify_csrf_for_session(request)
                except HTTPException as exc:
                    _log_csrf_rejection(request, exc)
                    return api_error_response(
                        exc.status_code,
                        "csrf_rejected",
                        error_message(exc.detail),
                    )
        return await call_next(request)

    # -------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """健康检查"""
        try:
            identity = runtime_projection() if runtime_projection is not None else {}
        except (OSError, RuntimeError, ValueError):
            identity = {}
        instance_id = identity.get("instance_id")
        generation = identity.get("generation")
        return HealthResponse(
            status="ok",
            engine_ready=engine_ready(),
            godot_web_ready=godot_web_ready(),
            godot_runtime_ready=godot_runtime_ready(),
            instance_id=(
                instance_id
                if isinstance(instance_id, str) and instance_id
                else "unavailable"
            ),
            generation=(
                generation
                if isinstance(generation, int) and not isinstance(generation, bool)
                else 0
            ),
        )

    # -------------------------------------------------------------------
    # Setup Wizard 路由（首启向导 — 在 owner 路由之前注册）
    # -------------------------------------------------------------------
    from .v1.admin.elfies import router as admin_elfies_router  # noqa: PLC0415
    from .v1.admin.food_packages import (
        router as food_packages_router,  # noqa: PLC0415
    )
    from .v1.admin.model_providers import (
        router as model_providers_router,  # noqa: PLC0415
    )
    from .v1.admin.nest import router as nest_management_router  # noqa: PLC0415
    from .v1.admin.runtime import router as runtime_router  # noqa: PLC0415
    from .v1.admin.runtime.embodiment_sessions import (
        router as embodiment_sessions_router,  # noqa: PLC0415
    )
    from .v1.admin.settings import router as settings_router  # noqa: PLC0415
    from .v1.admin.settings.capabilities import (
        router as capabilities_router,  # noqa: PLC0415
    )
    from .v1.admin.users import router as admin_users_router  # noqa: PLC0415
    from .v1.auth.routes import router as auth_router  # noqa: PLC0415
    from .v1.elfies import router as elfies_router  # noqa: PLC0415
    from .v1.elfies.bodies import router as bodies_router  # noqa: PLC0415
    from .v1.elfies.communication_accounts import (
        router as elfie_communication_accounts_router,  # noqa: PLC0415
    )
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
    from .v1.realtime.chat import router as realtime_chat_router  # noqa: PLC0415
    from .v1.setup import router as setup_router  # noqa: PLC0415

    app.include_router(auth_router)
    app.include_router(settings_router)
    app.include_router(nest_management_router)
    app.include_router(model_providers_router)
    app.include_router(food_packages_router)
    app.include_router(elfie_food_policy_router)
    app.include_router(elfie_communication_accounts_router)
    app.include_router(bodies_router)
    app.include_router(capabilities_router)
    app.include_router(runtime_router)
    app.include_router(embodiment_sessions_router)
    app.include_router(me_router)
    app.include_router(adoption_router)
    app.include_router(conversations_router)
    app.include_router(observer_router)
    app.include_router(realtime_chat_router)
    app.include_router(body_realtime_router)
    app.include_router(elfies_router)
    app.include_router(admin_elfies_router)
    app.include_router(admin_users_router)
    app.include_router(setup_router)
    app.include_router(page_router)
    return app
