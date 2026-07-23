"""Elfie Lab 本机网络边界。"""

from __future__ import annotations

import argparse
from ipaddress import ip_address

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp


def is_loopback_host(value: str) -> bool:
    """Return whether a hostname is restricted to the local machine."""
    host = value.strip()
    if host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def loopback_host(value: str) -> str:
    """Parse a host that cannot expose the unauthenticated Lab remotely."""
    host = value.strip()
    if not is_loopback_host(host):
        raise argparse.ArgumentTypeError("Elfie Lab 只能绑定本地回环地址")
    return host


class LoopbackHostMiddleware(BaseHTTPMiddleware):
    """Reject DNS-rebinding requests whose HTTP Host is not loopback."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        hostname = request.url.hostname or ""
        if not is_loopback_host(hostname):
            return PlainTextResponse("Invalid host header", status_code=400)
        return await call_next(request)
