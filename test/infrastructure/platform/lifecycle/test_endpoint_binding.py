from __future__ import annotations

import socket

import pytest

from infrastructure.platform.lifecycle.endpoint_binding import (
    EndpointBindError,
    bind_service_endpoints,
)


def test_explicit_pair_is_reserved_and_exposes_actual_ports() -> None:
    endpoints = bind_service_endpoints(0, 0)

    try:
        assert endpoints.http_port > 0
        assert endpoints.websocket_port > 0
        assert endpoints.http_port != endpoints.websocket_port
        assert endpoints.http.getsockname()[0] == "127.0.0.1"
    finally:
        endpoints.close()


def test_explicit_conflict_is_strict_and_never_relocated() -> None:
    occupant = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupant.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupant.bind(("127.0.0.1", 0))
    occupied_port = int(occupant.getsockname()[1])
    occupant.listen(1)

    try:
        with pytest.raises(EndpointBindError):
            bind_service_endpoints(occupied_port, occupied_port + 1)
    finally:
        occupant.close()


def test_automatic_pair_relocates_after_preflight_race() -> None:
    occupant = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupant.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupant.bind(("127.0.0.1", 0))
    occupied_port = int(occupant.getsockname()[1])
    occupant.listen(1)
    endpoints = None

    try:
        endpoints = bind_service_endpoints(
            occupied_port,
            occupied_port + 1,
            automatic=True,
        )
        assert endpoints.http_port != occupied_port
        assert endpoints.websocket_port != occupied_port
        assert endpoints.http_port != endpoints.websocket_port
    finally:
        if endpoints is not None:
            endpoints.close()
        occupant.close()
