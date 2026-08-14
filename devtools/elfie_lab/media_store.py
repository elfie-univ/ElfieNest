"""Elfie Lab 的内容寻址媒体存储。"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Final, NamedTuple

MAX_MEDIA_BYTES: Final = 5 * 1024 * 1024
_ELFIE_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_MEDIA_ID_PATTERN: Final = re.compile(r"^media_[0-9a-f]{64}$")
_URI_SCHEME: Final = "elfie-media"


class MediaStoreError(Exception):
    """媒体存储边界的基础错误。"""


class InvalidElfieIdError(MediaStoreError):
    __slots__ = ("elfie_id",)

    def __init__(self, elfie_id: str) -> None:
        self.elfie_id = elfie_id
        super().__init__(elfie_id)

    def __str__(self) -> str:
        return "无效的精灵本地数据标识"


class InvalidMediaIdError(MediaStoreError):
    __slots__ = ("media_id",)

    def __init__(self, media_id: str) -> None:
        self.media_id = media_id
        super().__init__(media_id)

    def __str__(self) -> str:
        return "无效的媒体标识"


class UnsupportedMediaError(MediaStoreError):
    __slots__ = ()

    def __str__(self) -> str:
        return "只支持 PNG、JPEG、WebP、PDF 或 UTF-8 文本附件"


class MediaTooLargeError(MediaStoreError):
    __slots__ = ("actual_bytes", "maximum_bytes")

    def __init__(self, actual_bytes: int, maximum_bytes: int = MAX_MEDIA_BYTES) -> None:
        self.actual_bytes = actual_bytes
        self.maximum_bytes = maximum_bytes
        super().__init__(actual_bytes, maximum_bytes)

    def __str__(self) -> str:
        return f"附件不能超过 {self.maximum_bytes} 字节"


class MediaNotFoundError(MediaStoreError):
    __slots__ = ("media_id",)

    def __init__(self, media_id: str) -> None:
        self.media_id = media_id
        super().__init__(media_id)

    def __str__(self) -> str:
        return f"媒体不存在: {self.media_id}"


class MediaDescriptor(NamedTuple):
    """可安全持久化并转换为 ``MediaRef`` 的媒体描述符。"""

    media_id: str
    uri: str
    mime_type: str
    size_bytes: int
    sha256: str


class _MediaFormat(NamedTuple):
    extension: str
    mime_type: str
    magic: bytes
    magic_offset: int = 0
    secondary_magic: bytes = b""
    secondary_offset: int = 0

    def matches(self, content: bytes) -> bool:
        end = self.magic_offset + len(self.magic)
        secondary_end = self.secondary_offset + len(self.secondary_magic)
        return (
            content[self.magic_offset : end] == self.magic
            and content[self.secondary_offset : secondary_end] == self.secondary_magic
        )


_BINARY_FORMATS: Final = (
    _MediaFormat(extension="png", mime_type="image/png", magic=b"\x89PNG\r\n\x1a\n"),
    _MediaFormat(extension="jpg", mime_type="image/jpeg", magic=b"\xff\xd8\xff"),
    _MediaFormat(
        extension="webp",
        mime_type="image/webp",
        magic=b"RIFF",
        secondary_magic=b"WEBP",
        secondary_offset=8,
    ),
    _MediaFormat(extension="pdf", mime_type="application/pdf", magic=b"%PDF-"),
)
_TEXT_FORMAT: Final = _MediaFormat(
    extension="txt",
    mime_type="text/plain",
    magic=b"",
)
_MEDIA_FORMATS: Final = (*_BINARY_FORMATS, _TEXT_FORMAT)


class ElfieLabMediaStore:
    """在 Lab 数据根目录内按内容哈希原子保存媒体。"""

    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir).expanduser()
        self.media_dir = self.root / "media"

    def store(self, elfie_id: str, content: bytes) -> MediaDescriptor:
        """校验媒体内容并返回不含本机绝对路径的稳定描述符。"""
        self._require_elfie_id(elfie_id)
        if len(content) > MAX_MEDIA_BYTES:
            raise MediaTooLargeError(actual_bytes=len(content))

        media_format = self._detect_format(content)
        digest = hashlib.sha256(content).hexdigest()
        media_id = f"media_{digest}"
        directory = self.media_dir / elfie_id
        destination = directory / f"{digest}.{media_format.extension}"
        descriptor = MediaDescriptor(
            media_id=media_id,
            uri=f"{_URI_SCHEME}://{elfie_id}/{destination.name}",
            mime_type=media_format.mime_type,
            size_bytes=len(content),
            sha256=digest,
        )
        if destination.exists():
            return descriptor

        directory.mkdir(parents=True, exist_ok=True)
        descriptor_number, temporary = tempfile.mkstemp(
            prefix=f".{digest}.", suffix=".tmp", dir=str(directory)
        )
        try:
            with os.fdopen(descriptor_number, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return descriptor

    def path_for(self, elfie_id: str, media_id: str) -> Path:
        """解析属于指定精灵的媒体 ID，不接受路径片段。"""
        self._require_elfie_id(elfie_id)
        if _MEDIA_ID_PATTERN.fullmatch(media_id) is None:
            raise InvalidMediaIdError(media_id=media_id)
        digest = media_id.removeprefix("media_")
        for media_format in _MEDIA_FORMATS:
            candidate = self.media_dir / elfie_id / f"{digest}.{media_format.extension}"
            if candidate.is_file():
                return candidate
        raise MediaNotFoundError(media_id=media_id)

    def descriptor_for(self, elfie_id: str, media_id: str) -> MediaDescriptor:
        """重新构造安全描述符，供回合请求按 ID 引用已上传媒体。"""
        path = self.path_for(elfie_id, media_id)
        mime_by_suffix = {
            f".{item.extension}": item.mime_type for item in _MEDIA_FORMATS
        }
        digest = media_id.removeprefix("media_")
        return MediaDescriptor(
            media_id=media_id,
            uri=f"{_URI_SCHEME}://{elfie_id}/{path.name}",
            mime_type=mime_by_suffix[path.suffix],
            size_bytes=path.stat().st_size,
            sha256=digest,
        )

    @staticmethod
    def _require_elfie_id(elfie_id: str) -> None:
        if _ELFIE_ID_PATTERN.fullmatch(elfie_id) is None:
            raise InvalidElfieIdError(elfie_id=elfie_id)

    @staticmethod
    def _detect_format(content: bytes) -> _MediaFormat:
        for media_format in _BINARY_FORMATS:
            if media_format.matches(content):
                return media_format
        if content and not content.startswith(b"data:") and b"\x00" not in content:
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                return _TEXT_FORMAT
        raise UnsupportedMediaError


__all__ = (
    "MAX_MEDIA_BYTES",
    "ElfieLabMediaStore",
    "InvalidElfieIdError",
    "InvalidMediaIdError",
    "MediaDescriptor",
    "MediaNotFoundError",
    "MediaStoreError",
    "MediaTooLargeError",
    "UnsupportedMediaError",
)
