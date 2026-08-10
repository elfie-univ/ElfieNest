"""Server-side page entry routes and safe post-login destinations."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from app.features.accounts import AccountPrincipal
from app.features.setup import GetSetupStatusQuery, SetupService
from app.interfaces.api.v1.auth import get_current_user
from app.interfaces.web.build_discovery import (
    WebBuildManifestMalformedError,
    WebBuildManifestMissingError,
    discover_web_build,
)

router = APIRouter(include_in_schema=False)

_SAFE_NEXT_PATHS = frozenset({"/chat", "/manage", "/monitor"})
_SHELL_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


def safe_next_path(raw_next: Optional[str]) -> Optional[str]:
    """Return a local, known page target or discard an untrusted next value."""
    if raw_next in _SAFE_NEXT_PATHS:
        return raw_next
    return None


def default_landing_path(user: AccountPrincipal) -> str:
    """Resolve the current role's server-enforced default landing page."""
    if user.role in {"owner", "admin"}:
        preference = user.default_landing_page
        if preference == "chat":
            return "/chat"
        return "/manage"
    return "/chat"


def post_login_landing_path(
    user: AccountPrincipal, raw_next: Optional[str]
) -> str:
    """Resolve login landing without letting generic chat redirects steal Owner flow."""
    safe_next = safe_next_path(raw_next)
    if user.role in {"owner", "admin"} and safe_next == "/manage":
        return "/manage"
    if user.role in {"owner", "admin"} and safe_next == "/monitor":
        return "/monitor"
    if user.role == "user" and safe_next == "/chat":
        return "/chat"
    return default_landing_path(user)


def _login_redirect(target: str) -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={target}", status_code=303)


def _current_page_user(request: Request) -> Optional[AccountPrincipal]:
    """Translate an absent or expired session into the page-login flow."""
    try:
        return get_current_user(request)
    except HTTPException as error:
        if error.status_code == 401:
            return None
        raise


def _serve_generated_page(request: Request) -> Response:
    """Return a generated page shell or a useful build diagnosis, never old assets."""
    web_build = getattr(request.app.state, "web_build", None)
    if web_build is None:
        error = getattr(
            request.app.state, "web_build_error", "Web build is unavailable."
        )
        return PlainTextResponse(str(error), status_code=503)
    return FileResponse(
        web_build.shell_path(),
        media_type="text/html",
        headers=_SHELL_CACHE_HEADERS,
    )


def _needs_setup(request: Request) -> bool:
    service = getattr(request.app.state, "setup", None)
    if not isinstance(service, SetupService):
        raise HTTPException(status_code=503, detail="Setup service unavailable")
    return service.get_status(GetSetupStatusQuery()).need_setup


@router.get("/assets/{asset_path:path}")
async def generated_asset(asset_path: str, request: Request) -> Response:
    """Serve manifest-listed static bundle assets; APIs enforce all data permissions."""
    web_build = getattr(request.app.state, "web_build", None)
    if web_build is None:
        error = getattr(
            request.app.state, "web_build_error", "Web build is unavailable."
        )
        return PlainTextResponse(str(error), status_code=503)
    try:
        path = web_build.asset_path(f"assets/{asset_path}")
    except FileNotFoundError as error:
        try:
            refreshed_build = discover_web_build(web_build.directory)
            path = refreshed_build.asset_path(f"assets/{asset_path}")
        except (
            FileNotFoundError,
            WebBuildManifestMalformedError,
            WebBuildManifestMissingError,
        ) as refresh_error:
            raise HTTPException(
                status_code=404, detail="页面资源不存在"
            ) from refresh_error
        request.app.state.web_build = refreshed_build
    return FileResponse(path)


@router.get("/")
async def root_page(request: Request) -> Response:
    """Send setup installs to setup and authenticated users to their landing page."""
    if _needs_setup(request):
        return RedirectResponse("/setup", status_code=303)
    user = _current_page_user(request)
    if user is None:
        return _login_redirect("/chat")
    return RedirectResponse(default_landing_path(user), status_code=303)


@router.get("/setup")
async def setup_page(request: Request) -> Response:
    """Serve the first-run React wizard only while no account exists."""
    if not _needs_setup(request):
        user = _current_page_user(request)
        return (
            RedirectResponse(default_landing_path(user), status_code=303)
            if user
            else _login_redirect("/chat")
        )
    return _serve_generated_page(request)


@router.get("/login")
async def login_page(request: Request) -> Response:
    """Serve the login-capable console, never reflecting an unsafe next target."""
    if _needs_setup(request):
        return RedirectResponse("/setup", status_code=303)
    user = _current_page_user(request)
    if user is not None:
        return RedirectResponse(default_landing_path(user), status_code=303)
    return _serve_generated_page(request)


@router.get("/chat")
async def chat_page(request: Request) -> Response:
    """Serve chat only to a valid session."""
    if _needs_setup(request):
        return RedirectResponse("/setup", status_code=303)
    if _current_page_user(request) is None:
        return _login_redirect("/chat")
    return _serve_generated_page(request)


@router.get("/manage")
async def manage_page(request: Request) -> Response:
    """Enforce the manager-only management landing route on the server."""
    if _needs_setup(request):
        return RedirectResponse("/setup", status_code=303)
    user = _current_page_user(request)
    if user is None:
        return _login_redirect("/manage")
    if user.role not in {"owner", "admin"}:
        return RedirectResponse("/chat", status_code=303)
    return _serve_generated_page(request)


@router.get("/monitor")
async def monitor_page(request: Request) -> Response:
    """Enforce the manager-only monitor landing route on the server."""
    if _needs_setup(request):
        return RedirectResponse("/setup", status_code=303)
    user = _current_page_user(request)
    if user is None:
        return _login_redirect("/monitor")
    if user.role not in {"owner", "admin"}:
        return RedirectResponse("/chat", status_code=303)
    return _serve_generated_page(request)
