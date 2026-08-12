"""Credential-safe HTTP transport for configured model providers."""

from __future__ import annotations

import time
from types import TracebackType
from typing import Final, Optional, Protocol, Type, cast
from urllib.request import HTTPRedirectHandler, Request, build_opener

_READ_CHUNK_BYTES: Final[int] = 64 * 1024


class ProviderHttpResponse(Protocol):
    status: int

    def read(self, amount: Optional[int] = None) -> bytes: ...

    def read1(self, amount: int = -1) -> bytes: ...

    def __enter__(self) -> ProviderHttpResponse: ...

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]: ...


class RejectProviderRedirects(HTTPRedirectHandler):
    """Turn redirects into HTTP errors so credentials never cross origins."""

    def redirect_request(
        self,
        request: Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        return None


_PROVIDER_OPENER = build_opener(RejectProviderRedirects())


def open_provider_request(request: Request, *, timeout: float) -> ProviderHttpResponse:
    """Open one Provider request without following any HTTP redirect."""
    return cast(
        ProviderHttpResponse,
        _PROVIDER_OPENER.open(request, timeout=timeout),
    )


def read_provider_response(
    response: ProviderHttpResponse,
    *,
    max_bytes: int,
    deadline_seconds: float,
) -> bytes:
    """Read a response with hard size and wall-clock bounds."""
    read1 = getattr(type(response), "read1", None)
    if not callable(read1):
        payload_bytes = response.read(max_bytes + 1)
        if len(payload_bytes) > max_bytes:
            raise ValueError("Provider 响应体超过安全上限")
        return payload_bytes

    deadline = time.monotonic() + deadline_seconds
    payload = bytearray()
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("Provider 响应读取超时")
        allowance = max_bytes + 1 - len(payload)
        chunk = read1(response, min(_READ_CHUNK_BYTES, allowance))
        if not chunk:
            return bytes(payload)
        payload.extend(chunk)
        if len(payload) > max_bytes:
            raise ValueError("Provider 响应体超过安全上限")
