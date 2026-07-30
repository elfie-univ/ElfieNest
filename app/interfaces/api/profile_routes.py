"""Authenticated local avatar upload and delivery endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Final, Optional, Protocol

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from typing_extensions import Annotated, TypedDict

from ai_runtime.storage.data_layout import ensure_final_user_layout, final_root_layout
from app.features.accounts.auth import get_current_user
from app.infrastructure.persistence.interface_query_repository import (
    InterfaceQueryRepository,
)

router = APIRouter(prefix="/api/auth/me", tags=["account-avatar"])

_MAX_AVATAR_BYTES: Final[int] = 2 * 1024 * 1024
_AVATAR_READ_CHUNK: Final[int] = 64 * 1024
_AVATAR_EXTENSIONS: Final[dict[str, str]] = {
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
}


def _matches_image_signature(content_type: str, image: bytes) -> bool:
    if content_type == "image/png":
        return image.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return image.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(image) >= 12 and image[:4] == b"RIFF" and image[8:12] == b"WEBP"
    return False


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


def _data_home(db_path: str) -> Path:
    return Path(db_path).expanduser().resolve().parent


async def _read_avatar_limited(file: AvatarUpload) -> bytes:
    """Read at most the configured limit plus one detection byte."""
    image = bytearray()
    while len(image) <= _MAX_AVATAR_BYTES:
        remaining = _MAX_AVATAR_BYTES + 1 - len(image)
        chunk = await file.read(min(_AVATAR_READ_CHUNK, remaining))
        if not chunk:
            break
        image.extend(chunk)
    if not image or len(image) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="头像不能为空且不得超过 2 MiB")
    return bytes(image)


@router.post("/avatar", status_code=201)
async def upload_avatar(
    request: Request,
    file: Annotated[UploadFile, File()],
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    """Store one validated local image for the authenticated account."""
    extension = _AVATAR_EXTENSIONS.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="头像仅支持 PNG、JPEG 或 WebP 图片")
    image = await _read_avatar_limited(file)
    if not _matches_image_signature(file.content_type or "", image):
        raise HTTPException(status_code=415, detail="头像内容与图片格式不匹配")
    user_id = int(user["id"])
    data_home = _data_home(request.app.state.db_path)
    user_layout = ensure_final_user_layout(data_home, str(user_id))
    for existing in user_layout.assets.glob("avatar.*"):
        existing.unlink()
    target = user_layout.avatar(extension)
    target.write_bytes(image)
    InterfaceQueryRepository(request.app.state.db_path).update_avatar_path(
        user_id, str(target.relative_to(data_home))
    )
    return {"avatar_url": "/api/auth/me/avatar"}


@router.get("/avatar")
async def current_avatar(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> FileResponse:
    """Serve only the current user's local avatar image."""
    user_id = int(user["id"])
    record = InterfaceQueryRepository(request.app.state.db_path).get_user(user_id)
    avatar_path = None if record is None else record.avatar_path
    if not avatar_path:
        raise HTTPException(status_code=404, detail="尚未上传头像")
    candidate = (
        final_root_layout(_data_home(request.app.state.db_path))
        .user(str(user_id))
        .assets
        / Path(avatar_path).name
    )
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="头像文件不存在")
    return FileResponse(candidate, headers={"Cache-Control": "no-store"})
