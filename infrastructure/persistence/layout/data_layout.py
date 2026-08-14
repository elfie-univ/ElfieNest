"""Pure path contract and secure directory creation for final product data."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable

_USER_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]+$")
_ELFIE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]{8}$")
_AVATAR_EXTENSIONS: Final[frozenset[str]] = frozenset({"png", "jpeg", "webp"})
_DIRECTORY_MODE: Final[int] = 0o700


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__.
class InvalidFinalUserIdError(ValueError):
    """A user ID cannot be used in the final asset layout."""

    user_id: str
    __slots__ = ("user_id",)

    def __str__(self) -> str:
        return f"final user ID must contain ASCII digits only: {self.user_id!r}"


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__.
class InvalidFinalElfieIdError(ValueError):
    """An Elfie ID cannot be used in the final workspace layout."""

    elfie_id: str
    __slots__ = ("elfie_id",)

    def __str__(self) -> str:
        return (
            f"final Elfie ID must contain exactly eight ASCII digits: {self.elfie_id!r}"
        )


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__.
class InvalidAvatarExtensionError(ValueError):
    """An avatar extension is outside the final image allowlist."""

    extension: str
    __slots__ = ("extension",)

    def __str__(self) -> str:
        return f"avatar extension must be png, jpeg, or webp: {self.extension!r}"


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__.
class UnsafeDataLayoutPathError(ValueError):
    """A final data directory is a symlink or a non-directory entry."""

    path: Path
    __slots__ = ("path",)

    def __str__(self) -> str:
        return f"final data directory must be a real directory, not a symlink or file: {self.path}"


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__.
class FinalUserLayout:
    """Resolved final paths for one user's managed assets."""

    assets: Path
    __slots__ = ("assets",)

    @property
    def files(self) -> Path:
        return self.assets / "files"

    def avatar(self, extension: str) -> Path:
        normalized = extension.lower()
        if normalized not in _AVATAR_EXTENSIONS:
            raise InvalidAvatarExtensionError(extension)
        return self.assets / f"avatar.{normalized}"


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__.
class FinalElfieLayout:
    """Resolved final paths for one stable Elfie workspace."""

    workspace: Path
    __slots__ = ("workspace",)

    @property
    def assets(self) -> Path:
        return self.workspace / "assets"

    @property
    def godot(self) -> Path:
        return self.workspace / "godot"

    @property
    def profile(self) -> Path:
        return self.workspace / "profile" / "profile.yaml"

    @property
    def skills(self) -> Path:
        return self.workspace / "skills"

    @property
    def history_database(self) -> Path:
        return self.workspace / "conversations" / "history.sqlite"

    @property
    def attachments(self) -> Path:
        return self.workspace / "conversations" / "attachments"

    @property
    def portrait_headshot(self) -> Path:
        return self.assets / "portrait-head.png"

    @property
    def portrait_full_body(self) -> Path:
        return self.assets / "portrait-full.png"

    @property
    def knowledge_database(self) -> Path:
        return self.workspace / "memory" / "knowledge.sqlite"

    @property
    def daily_memory(self) -> Path:
        return self.workspace / "memory" / "daily"

    @property
    def people_memory(self) -> Path:
        return self.workspace / "memory" / "people"

    @property
    def concepts_memory(self) -> Path:
        return self.workspace / "memory" / "concepts"


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__.
class FinalRootLayout:
    """Resolved final paths below one explicit product data root."""

    data_home: Path
    __slots__ = ("data_home",)

    @property
    def nest_database(self) -> Path:
        return self.data_home / "nest.db"

    @property
    def providers_config(self) -> Path:
        return self.data_home / "configs" / "providers.yaml"

    @property
    def auth_env(self) -> Path:
        return self.data_home / "configs" / "auth.env"

    @property
    def oauth_credentials(self) -> Path:
        return self.data_home / "configs" / "credentials" / "oauth"

    @property
    def runtime_config(self) -> Path:
        return self.data_home / "configs" / "runtime.yaml"

    @property
    def model_validations(self) -> Path:
        return self.data_home / "reports" / "model-validations"

    @property
    def runtime_validations(self) -> Path:
        return self.data_home / "reports" / "runtime-validations"

    @property
    def runtime_state(self) -> Path:
        return self.data_home / "runtime" / "runtime.json"

    @property
    def runtime_locks(self) -> Path:
        return self.data_home / "runtime" / "locks"

    @property
    def token_usage_log(self) -> Path:
        return self.data_home / "logs" / "token_usage.jsonl"

    def user(self, user_id: str) -> FinalUserLayout:
        if _USER_ID_PATTERN.fullmatch(user_id) is None:
            raise InvalidFinalUserIdError(user_id)
        return FinalUserLayout(self.data_home / "assets" / "users" / user_id)

    def elfie(self, elfie_id: str) -> FinalElfieLayout:
        if _ELFIE_ID_PATTERN.fullmatch(elfie_id) is None:
            raise InvalidFinalElfieIdError(elfie_id)
        return FinalElfieLayout(self.data_home / "elfies" / elfie_id)


def final_root_layout(data_home: Path) -> FinalRootLayout:
    """Resolve final paths without reading environment variables or writing data."""
    return FinalRootLayout(data_home.expanduser())


def _root_directories(layout: FinalRootLayout) -> tuple[Path, ...]:
    root = layout.data_home
    return (
        root,
        root / "configs",
        root / "configs" / "credentials",
        layout.oauth_credentials,
        root / "reports",
        layout.model_validations,
        layout.runtime_validations,
        root / "assets",
        root / "assets" / "users",
        root / "elfies",
        root / "runtime",
        layout.runtime_locks,
        root / "logs",
    )


def _ensure_directories(paths: Iterable[Path]) -> None:
    directories = tuple(paths)
    for path in directories:
        for candidate in (path, *path.parents):
            if candidate.is_symlink() or (
                candidate.exists() and not candidate.is_dir()
            ):
                raise UnsafeDataLayoutPathError(candidate)
    for path in directories:
        path.mkdir(mode=_DIRECTORY_MODE, exist_ok=True)
        os.chmod(path, _DIRECTORY_MODE, follow_symlinks=False)


def ensure_final_root_layout(data_home: Path) -> FinalRootLayout:
    """Create the final shared directories with owner-only permissions."""
    layout = final_root_layout(data_home)
    _ensure_directories(_root_directories(layout))
    return layout


def ensure_final_user_layout(data_home: Path, user_id: str) -> FinalUserLayout:
    """Create one parsed user's final asset directories."""
    root_layout = final_root_layout(data_home)
    user_layout = root_layout.user(user_id)
    _ensure_directories(
        (*_root_directories(root_layout), user_layout.assets, user_layout.files)
    )
    return user_layout


def ensure_final_elfie_layout(data_home: Path, elfie_id: str) -> FinalElfieLayout:
    """Create one parsed Elfie's final workspace directories."""
    root_layout = final_root_layout(data_home)
    elfie_layout = root_layout.elfie(elfie_id)
    workspace_directories = (
        elfie_layout.workspace,
        elfie_layout.assets,
        elfie_layout.godot,
        elfie_layout.profile.parent,
        elfie_layout.skills,
        elfie_layout.history_database.parent,
        elfie_layout.attachments,
        elfie_layout.knowledge_database.parent,
        elfie_layout.daily_memory,
        elfie_layout.people_memory,
        elfie_layout.concepts_memory,
    )
    _ensure_directories((*_root_directories(root_layout), *workspace_directories))
    return elfie_layout
