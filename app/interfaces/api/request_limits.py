"""Small ASGI request limits that must run before multipart parsing."""

from __future__ import annotations

import asyncio
from typing import Final

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.interfaces.api.v1.auth import verify_csrf_token

_AVATAR_UPLOAD_PATH: Final[str] = "/api/auth/me/avatar"
_MAX_AVATAR_REQUEST_BYTES: Final[int] = 2 * 1024 * 1024 + 64 * 1024
_MAX_ACTIVE_UPLOADS: Final[int] = 4
_UPLOAD_BODY_DEADLINE_SECONDS: Final[float] = 10.0


class AvatarUploadBodyLimitMiddleware:
    """Bound avatar multipart bodies before Starlette creates an UploadFile."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._active_uploads = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._targets_avatar_upload(scope):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        session_token = request.cookies.get("session_token", "")
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not session_token or not verify_csrf_token(session_token, csrf_token):
            await self._respond(scope, receive, send, 403, "CSRF token 无效")
            return
        if self._active_uploads >= _MAX_ACTIVE_UPLOADS:
            await self._respond(
                scope, receive, send, 429, "头像上传任务过多，请稍后重试"
            )
            return
        content_length = self._content_length(scope)
        if content_length is not None and content_length > _MAX_AVATAR_REQUEST_BYTES:
            await self._respond(scope, receive, send, 413, "头像上传请求不得超过 2 MiB")
            return
        self._active_uploads += 1
        try:
            body = await asyncio.wait_for(
                self._read_body(receive), timeout=_UPLOAD_BODY_DEADLINE_SECONDS
            )
        except asyncio.TimeoutError:
            await self._respond(scope, receive, send, 408, "头像上传超时")
            return
        finally:
            self._active_uploads -= 1
        if body is None:
            await self._respond(scope, receive, send, 413, "头像上传请求不得超过 2 MiB")
            return

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    @staticmethod
    def _targets_avatar_upload(scope: Scope) -> bool:
        return (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == _AVATAR_UPLOAD_PATH
        )

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                return int(value)
            except ValueError:
                return None
        return None

    async def _read_body(self, receive: Receive) -> bytes | None:
        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return None
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > _MAX_AVATAR_REQUEST_BYTES:
                return None
            body.extend(chunk)
            more_body = bool(message.get("more_body", False))
        return bytes(body)

    @staticmethod
    async def _respond(
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": detail},
        )
        await response(scope, receive, send)
