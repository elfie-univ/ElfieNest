"""Server-side page entry routes and safe post-login destinations."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from app.features.accounts.auth import get_current_user
from app.features.setup.service import needs_setup
from app.interfaces.web import STATIC_DIR

router = APIRouter(include_in_schema=False)

_SAFE_NEXT_PATHS = frozenset({"/chat", "/manage"})


def safe_next_path(raw_next: Optional[str]) -> Optional[str]:
    """Return a local, known page target or discard an untrusted next value."""
    if raw_next in _SAFE_NEXT_PATHS:
        return raw_next
    return None


def default_landing_path(user: Dict[str, Any]) -> str:
    """Resolve the current role's server-enforced default landing page."""
    if user.get("role") == "owner":
        preference = user.get("default_landing_page")
        if preference == "chat":
            return "/chat"
        return "/manage"
    return "/chat"


def _login_redirect(target: str) -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={target}", status_code=303)


def _current_page_user(request: Request) -> Optional[Dict[str, Any]]:
    """Translate an absent or expired session into the page-login flow."""
    try:
        return get_current_user(request)
    except HTTPException as error:
        if error.status_code == 401:
            return None
        raise


def _serve_generated_page(request: Request, page: str) -> Response:
    """Return a generated page shell or a useful build diagnosis, never old assets."""
    web_build = getattr(request.app.state, "web_build", None)
    if web_build is None:
        error = getattr(request.app.state, "web_build_error", "Web build is unavailable.")
        return PlainTextResponse(str(error), status_code=503)
    return FileResponse(web_build.page_path(page), media_type="text/html")


@router.get("/assets/{asset_path:path}")
async def generated_asset(asset_path: str, request: Request) -> Response:
    """Serve only login assets anonymously; product-specific assets require a session."""
    web_build = getattr(request.app.state, "web_build", None)
    if web_build is None:
        error = getattr(request.app.state, "web_build_error", "Web build is unavailable.")
        return PlainTextResponse(str(error), status_code=503)
    user = _current_page_user(request)
    if user is None and not web_build.is_login_asset(f"assets/{asset_path}"):
        raise HTTPException(status_code=401, detail="登录后才能加载产品资源")
    try:
        path = web_build.asset_path(f"assets/{asset_path}")
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="页面资源不存在") from error
    return FileResponse(path)


@router.get("/")
async def root_page(request: Request) -> Response:
    """Send setup installs to setup and authenticated users to their landing page."""
    if needs_setup(request.app.state.db_path):
        return FileResponse(STATIC_DIR / "setup.html", media_type="text/html")
    user = _current_page_user(request)
    if user is None:
        return _login_redirect("/chat")
    return RedirectResponse(default_landing_path(user), status_code=303)


@router.get("/login")
async def login_page(request: Request) -> Response:
    """Serve the login-capable console, never reflecting an unsafe next target."""
    user = _current_page_user(request)
    if user is not None:
        return RedirectResponse(default_landing_path(user), status_code=303)
    return _serve_generated_page(request, "login.html")


@router.get("/chat")
async def chat_page(request: Request) -> Response:
    """Serve chat only to a valid session."""
    if _current_page_user(request) is None:
        return _login_redirect("/chat")
    return _serve_generated_page(request, "chat.html")


@router.get("/manage")
async def manage_page(request: Request) -> Response:
    """Enforce the Owner-only management landing route on the server."""
    user = _current_page_user(request)
    if user is None:
        return _login_redirect("/manage")
    if user.get("role") != "owner":
        return RedirectResponse("/chat", status_code=303)
    if request.query_params.get("mode") == "classic":
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")
    return _serve_generated_page(request, "manage.html")
