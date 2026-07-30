"""Validated storage paths and bytes for local account avatars."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Optional

MAX_AVATAR_BYTES: Final[int] = 2 * 1024 * 1024
AVATAR_READ_CHUNK: Final[int] = 64 * 1024
_CONTENT_TYPE_EXTENSIONS: Final[dict[str, str]] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {"jpg", "jpeg", "png", "webp"}
)


@dataclass(frozen=True)
class AvatarStorageError(RuntimeError):
    """An avatar path or payload violates the local storage contract."""

    reason: str
    __slots__ = ("reason",)

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True)
class AvatarCopy:
    """A fully validated legacy-to-final avatar copy operation."""

    source: Path
    target: Path
    relative_path: str
    image: bytes
    __slots__ = ("source", "target", "relative_path", "image")


def extension_for_content_type(content_type: str) -> Optional[str]:
    """Return the canonical stored extension for an accepted MIME type."""
    return _CONTENT_TYPE_EXTENSIONS.get(content_type)


def validate_avatar_image(extension: str, image: bytes) -> None:
    """Reject unsupported, empty, oversized, or signature-mismatched images."""
    normalized = extension.lower()
    if normalized not in _ALLOWED_EXTENSIONS:
        raise AvatarStorageError(f"unsupported avatar extension: {extension}")
    if not image or len(image) > MAX_AVATAR_BYTES:
        raise AvatarStorageError("avatar must contain at most 2 MiB")
    signature_matches = {
        "jpg": image.startswith(b"\xff\xd8\xff"),
        "jpeg": image.startswith(b"\xff\xd8\xff"),
        "png": image.startswith(b"\x89PNG\r\n\x1a\n"),
        "webp": len(image) >= 12
        and image[:4] == b"RIFF"
        and image[8:12] == b"WEBP",
    }[normalized]
    if not signature_matches:
        raise AvatarStorageError("avatar bytes do not match the stored extension")


def inspect_avatar_for_cutover(
    data_root: Path,
    user_id: int,
    stored_path: str,
) -> Optional[AvatarCopy]:
    """Validate one stored path and return a copy only for the legacy layout."""
    relative = PurePosixPath(stored_path)
    if relative.is_absolute() or "\\" in stored_path or ".." in relative.parts:
        raise AvatarStorageError("avatar path must be a safe relative path")
    final_prefix = ("assets", "users", str(user_id))
    legacy_prefix = ("avatars", "users")
    if relative.parts[:3] == final_prefix and len(relative.parts) == 4:
        extension = _avatar_filename_extension(relative.name, "avatar")
        _read_validated_avatar(data_root, relative, extension)
        return None
    if relative.parts[:2] != legacy_prefix or len(relative.parts) != 3:
        raise AvatarStorageError("avatar path is outside the supported user roots")
    extension = _avatar_filename_extension(relative.name, str(user_id))
    image = _read_validated_avatar(data_root, relative, extension)
    target_relative = PurePosixPath(
        "assets", "users", str(user_id), f"avatar.{extension}"
    )
    return AvatarCopy(
        source=data_root / relative,
        target=data_root / target_relative,
        relative_path=target_relative.as_posix(),
        image=image,
    )


def install_avatar_copy(copy: AvatarCopy) -> bool:
    """Install a validated copy and report whether a new target was created."""
    temporary = copy.target.with_name(f".{copy.target.name}.card15.tmp")
    try:
        data_root = copy.target.parents[3]
        _assert_safe_directory(data_root, copy.target.parent)
        copy.target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if copy.target.exists():
            if copy.target.is_symlink():
                raise AvatarStorageError("avatar target cannot be a symlink")
            if copy.target.read_bytes() == copy.image:
                return False
            raise AvatarStorageError("avatar target already contains different bytes")
        temporary.write_bytes(copy.image)
        temporary.replace(copy.target)
        return True
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise AvatarStorageError(f"avatar copy failed: {error}") from error


def store_user_avatar(
    db_path: str,
    user_id: int,
    extension: str,
    image: bytes,
) -> str:
    """Write the authenticated user's avatar only in the final asset layout."""
    validate_avatar_image(extension, image)
    data_root = Path(db_path).expanduser().resolve().parent
    target_dir = data_root / "assets" / "users" / str(user_id)
    target = target_dir / f"avatar.{extension.lower()}"
    temporary = target.with_name(f".{target.name}.upload.tmp")
    try:
        _assert_safe_directory(data_root, target_dir)
        target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.is_symlink():
            raise AvatarStorageError("avatar target cannot be a symlink")
        temporary.write_bytes(image)
        temporary.replace(target)
        for existing in target_dir.glob("avatar.*"):
            if existing != target and existing.is_file():
                existing.unlink()
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise AvatarStorageError(f"avatar upload failed: {error}") from error
    return target.relative_to(data_root).as_posix()


def resolve_user_avatar(
    db_path: str,
    user_id: int,
    stored_path: str,
) -> Path:
    """Resolve and revalidate an avatar only from the final user asset path."""
    data_root = Path(db_path).expanduser().resolve().parent
    relative = PurePosixPath(stored_path)
    expected_prefix = ("assets", "users", str(user_id))
    if relative.parts[:3] != expected_prefix or len(relative.parts) != 4:
        raise AvatarStorageError("avatar path is not in the final user asset root")
    extension = _avatar_filename_extension(relative.name, "avatar")
    _assert_safe_directory(data_root, (data_root / relative).parent)
    _read_validated_avatar(data_root, relative, extension)
    return data_root / relative


def _avatar_filename_extension(filename: str, stem: str) -> str:
    prefix = f"{stem}."
    if not filename.startswith(prefix):
        raise AvatarStorageError("avatar filename does not match its account")
    extension = filename[len(prefix) :].lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise AvatarStorageError("avatar filename has an unsupported extension")
    return extension


def _read_validated_avatar(
    data_root: Path,
    relative: PurePosixPath,
    extension: str,
) -> bytes:
    candidate = data_root / relative
    _assert_safe_directory(data_root, candidate.parent)
    if candidate.is_symlink() or not candidate.is_file():
        raise AvatarStorageError("avatar source is missing or not a regular file")
    try:
        size = candidate.stat().st_size
        if size < 1 or size > MAX_AVATAR_BYTES:
            raise AvatarStorageError("avatar must contain at most 2 MiB")
        image = candidate.read_bytes()
    except OSError as error:
        raise AvatarStorageError(f"avatar could not be read: {error}") from error
    validate_avatar_image(extension, image)
    return image


def _assert_safe_directory(data_root: Path, directory: Path) -> None:
    root = data_root.resolve()
    try:
        relative = directory.relative_to(data_root)
        directory.resolve().relative_to(root)
    except ValueError as error:
        raise AvatarStorageError("avatar directory resolves outside the data root") from error
    current = data_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise AvatarStorageError("avatar directory ancestor cannot be a symlink")
