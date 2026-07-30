"""Authenticated local avatar upload and delivery endpoints."""

from __future__ import annotations

from typing import Optional, Protocol

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from typing_extensions import Annotated, TypedDict

from app.features.accounts.auth import get_current_user
from app.infrastructure.persistence.account_avatar_storage import (
    AVATAR_READ_CHUNK,
    MAX_AVATAR_BYTES,
    AvatarStorageError,
    extension_for_content_type,
    resolve_user_avatar,
    store_user_avatar,
)
from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.store import get_db

router = APIRouter(prefix="/api/auth/me", tags=["account-avatar"])

class AuthenticatedUser(TypedDict):
    id: int
    username: str
    role: str
    default_landing_page: str


class AvatarUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


def avatar_url(avatar_path: Optional[str]) -> Optional[str]:
    """Expose a same-origin route instead of any local filesystem path."""
    return "/api/auth/me/avatar" if avatar_path else None


async def _read_avatar_limited(file: AvatarUpload) -> bytes:
    """Read at most the configured limit plus one detection byte."""
    image = bytearray()
    while len(image) <= MAX_AVATAR_BYTES:
        remaining = MAX_AVATAR_BYTES + 1 - len(image)
        chunk = await file.read(min(AVATAR_READ_CHUNK, remaining))
        if not chunk:
            break
        image.extend(chunk)
    if not image or len(image) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="头像不能为空且不得超过 2 MiB")
    return bytes(image)


@router.post("/avatar", status_code=201)
async def upload_avatar(
    request: Request,
    file: Annotated[UploadFile, File()],
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    """Store one validated local image for the authenticated account."""
    extension = extension_for_content_type(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="头像仅支持 PNG、JPEG 或 WebP 图片")
    image = await _read_avatar_limited(file)
    try:
        relative_path = store_user_avatar(
            request.app.state.db_path, int(user["id"]), extension, image
        )
    except AvatarStorageError:
        raise HTTPException(
            status_code=415, detail="头像内容与图片格式不匹配"
        ) from None
    user_id = int(user["id"])
    with get_db(request.app.state.db_path) as conn:
        AccountRepository(conn).update_avatar_path(user_id, relative_path)
        conn.commit()
    return {"avatar_url": "/api/auth/me/avatar"}


@router.get("/avatar")
async def current_avatar(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> FileResponse:
    """Serve only the current user's local avatar image."""
    with get_db(request.app.state.db_path) as conn:
        account = AccountRepository(conn).find_by_id(int(user["id"]))
    avatar_path = account.avatar_path if account is not None else None
    if not avatar_path:
        raise HTTPException(status_code=404, detail="尚未上传头像")
    try:
        candidate = resolve_user_avatar(
            request.app.state.db_path, int(user["id"]), avatar_path
        )
    except AvatarStorageError:
        raise HTTPException(status_code=404, detail="头像文件不存在") from None
    return FileResponse(candidate, headers={"Cache-Control": "no-store"})
