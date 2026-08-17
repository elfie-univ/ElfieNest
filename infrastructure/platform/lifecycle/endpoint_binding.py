"""Core-owned TCP endpoint reservation for the Runtime services."""

from __future__ import annotations

import errno
import socket
from dataclasses import dataclass
from typing import Optional


class EndpointBindError(OSError):
    """Raised when the requested Runtime endpoint pair cannot be reserved."""


@dataclass
class BoundServiceEndpoints:
    """Listening sockets kept open until their owning services take them over."""

    http: socket.socket
    websocket: socket.socket

    @property
    def http_port(self) -> int:
        return int(self.http.getsockname()[1])

    @property
    def websocket_port(self) -> int:
        return int(self.websocket.getsockname()[1])

    def close(self) -> None:
        """Release both reservations exactly once."""
        for endpoint in (self.http, self.websocket):
            try:
                endpoint.close()
            except OSError:
                pass


def bind_service_endpoints(
    http_port: int,
    websocket_port: int,
    *,
    automatic: bool = False,
    host: str = "127.0.0.1",
) -> BoundServiceEndpoints:
    """Reserve both service endpoints before Core publishes readiness.

    Explicit ports are strict. Automatic mode first tries the selected pair and
    then lets the OS choose a fresh pair when a third-party process wins the
    preflight race. The sockets remain listening until HTTP and Gateway take
    ownership, so the later service starts cannot reopen a time-of-check race.
    """
    if http_port == websocket_port and http_port != 0:
        raise EndpointBindError("HTTP and WebSocket ports must be distinct")
    if not automatic:
        try:
            return _bind_pair(host, http_port, websocket_port)
        except OSError as error:
            raise EndpointBindError(str(error)) from error

    candidates = [(http_port, websocket_port)]
    # A pair of OS-selected ports is the bounded automatic fallback. Retrying
    # the pair keeps both endpoints owned by this Core generation.
    candidates.extend((0, 0) for _ in range(3))
    last_error: Optional[OSError] = None
    for candidate_http, candidate_websocket in candidates:
        try:
            endpoints = _bind_pair(host, candidate_http, candidate_websocket)
        except OSError as error:
            last_error = error
            if not _is_bind_conflict(error):
                raise EndpointBindError(str(error)) from error
            continue
        if endpoints.http_port == endpoints.websocket_port:
            endpoints.close()
            last_error = EndpointBindError("OS selected duplicate service ports")
            continue
        return endpoints
    detail = str(last_error or "unable to reserve service endpoints")
    raise EndpointBindError(detail) from last_error


def _bind_pair(host: str, http_port: int, websocket_port: int) -> BoundServiceEndpoints:
    http_socket: Optional[socket.socket] = None
    websocket_socket: Optional[socket.socket] = None
    try:
        http_socket = _bind_one(host, http_port)
        websocket_socket = _bind_one(host, websocket_port)
        return BoundServiceEndpoints(http=http_socket, websocket=websocket_socket)
    except OSError:
        if websocket_socket is not None:
            websocket_socket.close()
        if http_socket is not None:
            http_socket.close()
        raise


def _bind_one(host: str, port: int) -> socket.socket:
    endpoint = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        endpoint.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        endpoint.bind((host, port))
        endpoint.listen(128)
        return endpoint
    except OSError:
        endpoint.close()
        raise


def _is_bind_conflict(error: OSError) -> bool:
    return error.errno in {errno.EADDRINUSE, errno.EADDRNOTAVAIL}


__all__ = (
    "BoundServiceEndpoints",
    "EndpointBindError",
    "bind_service_endpoints",
)
