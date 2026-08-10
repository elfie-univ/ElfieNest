"""Core HTTP bind policy and request-host validation for local/LAN service modes."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Sequence, Tuple
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse


class ServiceMode(str, Enum):
    """Network exposure explicitly selected for the Core HTTP server."""

    LOOPBACK = "loopback"
    LAN = "lan"


LOOPBACK_HOSTS: Final[Tuple[str, ...]] = ("127.0.0.1", "localhost", "::1")
ANONYMOUS_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/login",
        "/api/v1/auth/login",
        "/api/auth/setup-status",
        "/api/health",
    }
)


def private_ipv4_addresses() -> Tuple[str, ...]:
    """Return addresses suitable for a private IPv4 LAN listener allowlist."""
    addresses: set[str] = set()
    try:
        candidates = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except socket.gaierror:
        candidates = []
    for candidate in candidates:
        address = str(candidate[4][0])
        if ipaddress.ip_address(address).is_private:
            addresses.add(address)
    return tuple(sorted(addresses))


@dataclass(frozen=True)
class ServiceAccessPolicy:
    """Trusted HTTP names and origins derived from an explicit bind mode."""

    mode: ServiceMode
    http_port: int
    hostnames: frozenset[str]

    @classmethod
    def create(
        cls,
        mode: str,
        http_port: int,
        lan_addresses: Optional[Sequence[str]] = None,
    ) -> ServiceAccessPolicy:
        selected_mode = ServiceMode(mode)
        hosts = set(LOOPBACK_HOSTS)
        if selected_mode is ServiceMode.LAN:
            hosts.update(
                lan_addresses if lan_addresses is not None else private_ipv4_addresses()
            )
        return cls(
            mode=selected_mode,
            http_port=http_port,
            hostnames=frozenset(hosts),
        )

    @property
    def cors_origins(self) -> Tuple[str, ...]:
        return tuple(
            sorted(f"http://{host}:{self.http_port}" for host in self.hostnames)
        )

    def allows_host(self, raw_host: str) -> bool:
        """Accept the configured hostname and, when supplied, HTTP port only."""
        hostname, port = _authority_parts(raw_host)
        return hostname in self.hostnames and port in (None, self.http_port)

    def allows_origin(self, raw_origin: str) -> bool:
        """Accept same-service HTTP origins; LAN intentionally has no HTTPS claim."""
        parsed = urlparse(raw_origin)
        try:
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and parsed.hostname in self.hostnames
            and port == self.http_port
            and not parsed.path
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
        )


def _authority_parts(authority: str) -> Tuple[str, Optional[int]]:
    """Parse Host authority without treating malformed names or ports as trusted."""
    parsed = urlparse(f"//{authority}")
    try:
        return parsed.hostname or "", parsed.port
    except ValueError:
        return "", None


def configure_service_access(app, policy: ServiceAccessPolicy) -> None:
    """Install host/origin guards and expose the policy to routers and CORS."""
    app.state.service_access_policy = policy
    app.state.anonymous_paths = ANONYMOUS_PATHS

    @app.middleware("http")
    async def enforce_host_and_origin(request: Request, call_next):
        if policy.mode is ServiceMode.LOOPBACK:
            return await call_next(request)
        host = request.headers.get("host", "")
        if not policy.allows_host(host):
            return JSONResponse(status_code=400, content={"detail": "不受信任的 Host"})
        origin = request.headers.get("origin")
        if origin and not policy.allows_origin(origin):
            return JSONResponse(
                status_code=403, content={"detail": "不受信任的 Origin"}
            )
        return await call_next(request)
