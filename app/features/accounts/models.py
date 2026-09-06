"""Commands, queries and results owned by Accounts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Literal, Optional, Tuple

from .roles import AccountRole


@dataclass(frozen=True)
class AccountPrincipal:
    """Authenticated product identity shared by App entry points."""

    user_id: int
    account_id: str
    role: AccountRole
    # Configuration-only principals do not need to carry a routing decision.
    # Real sessions still populate this from the users table.
    default_landing_page: str = "manage"


@dataclass(frozen=True)
class LoginCommand:
    account_id: str
    password: str
    client_key: str


@dataclass(frozen=True)
class RegisterAccountCommand:
    account_id: str
    display_name: str
    password: str


@dataclass(frozen=True)
class HasOwnerQuery:
    pass


@dataclass(frozen=True)
class CreateFirstOwnerCommand:
    account_id: str
    display_name: Optional[str]
    password_hash: str


@dataclass(frozen=True)
class SeedInitialOwnerCommand:
    pass


@dataclass(frozen=True)
class SeedInitialOwnerResult:
    created: bool


@dataclass(frozen=True)
class AuthenticatedSession:
    principal: AccountPrincipal
    display_name: str | None
    session_token: str
    ttl_seconds: int


@dataclass(frozen=True)
class SecurityPolicy:
    session_ttl_seconds: int
    max_login_attempts: int
    login_window_seconds: int


Gender = Literal["male", "female"]
AvatarKind = Literal["initials", "emoji"]
ThemeKey = Literal[
    "warm-paper",
    "harbor-blue",
    "orchid-archive",
    "moss-green",
]
LandingPage = Literal["chat", "manage"]
Presence = Literal["online", "away", "offline"]
ManagedAccountRole = Literal["admin", "user"]
ProfileField = Literal[
    "account_id",
    "display_name",
    "gender",
    "birth_date",
    "avatar_color",
    "avatar_kind",
]


@dataclass(frozen=True)
class GetCurrentAccountQuery:
    pass


@dataclass(frozen=True)
class RecordAccountHeartbeatCommand:
    pass


@dataclass(frozen=True)
class AccountHeartbeatResult:
    last_seen_at: str


@dataclass(frozen=True)
class AccountProfileResult:
    user_id: int
    account_id: str
    display_name: Optional[str]
    gender: Gender
    birth_date: Optional[str]
    role: AccountRole
    has_avatar: bool
    avatar_color: int
    avatar_kind: AvatarKind
    theme_key: ThemeKey
    default_landing_page: LandingPage
    created_at: str
    elfie_count: int


@dataclass(frozen=True)
class UpdateAccountProfileCommand:
    fields: FrozenSet[ProfileField] = field(default_factory=frozenset)
    account_id: Optional[str] = None
    display_name: Optional[str] = None
    gender: Optional[Gender] = None
    birth_date: Optional[str] = None
    avatar_color: Optional[int] = None
    avatar_kind: Optional[AvatarKind] = None


@dataclass(frozen=True)
class ChangePasswordCommand:
    old_password: str
    new_password: str
    current_session_token: str


@dataclass(frozen=True)
class UpdateThemeCommand:
    theme_key: ThemeKey


@dataclass(frozen=True)
class UpdateLandingPageCommand:
    default_landing_page: LandingPage


@dataclass(frozen=True)
class UploadAvatarCommand:
    content_type: str
    content: bytes


@dataclass(frozen=True)
class GetAvatarQuery:
    pass


@dataclass(frozen=True)
class GetManagedAvatarQuery:
    user_id: int


@dataclass(frozen=True)
class AvatarResult:
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ListManagedAccountsQuery:
    pass


@dataclass(frozen=True)
class ManagedAccountResult:
    user_id: int
    account_id: str
    display_name: Optional[str]
    role: AccountRole
    gender: Gender
    birth_date: Optional[str]
    presence: Presence
    last_seen_at: Optional[str]
    language: str
    created_at: str
    elfie_count: int
    elfie_quota_override: Optional[int]
    effective_elfie_limit: int
    has_avatar: bool


@dataclass(frozen=True)
class ManagedAccountsResult:
    items: Tuple[ManagedAccountResult, ...]


@dataclass(frozen=True)
class CreateManagedAccountCommand:
    account_id: str
    display_name: Optional[str]
    password: str
    role: ManagedAccountRole


@dataclass(frozen=True)
class UpdateManagedAccountQuotaCommand:
    user_id: int
    elfie_quota_override: Optional[int]


@dataclass(frozen=True)
class DeleteManagedAccountCommand:
    user_id: int


@dataclass(frozen=True)
class ResetManagedAccountPasswordCommand:
    user_id: int


@dataclass(frozen=True)
class TemporaryPasswordResult:
    temporary_password: str


@dataclass(frozen=True)
class GetOwnerAccountQuery:
    pass


@dataclass(frozen=True)
class RecoverOwnerAccountCommand:
    account_id: str
    new_password: str


@dataclass(frozen=True)
class OwnerAccountResult:
    user_id: int
    account_id: str
    display_name: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    password_status: str = "Set (not viewable)"


__all__ = (
    "AccountHeartbeatResult",
    "AccountProfileResult",
    "AccountPrincipal",
    "AuthenticatedSession",
    "AvatarKind",
    "AvatarResult",
    "ChangePasswordCommand",
    "CreateManagedAccountCommand",
    "CreateFirstOwnerCommand",
    "DeleteManagedAccountCommand",
    "Gender",
    "GetAvatarQuery",
    "GetCurrentAccountQuery",
    "GetManagedAvatarQuery",
    "HasOwnerQuery",
    "GetOwnerAccountQuery",
    "LandingPage",
    "ListManagedAccountsQuery",
    "LoginCommand",
    "ManagedAccountResult",
    "ManagedAccountRole",
    "ManagedAccountsResult",
    "OwnerAccountResult",
    "Presence",
    "ProfileField",
    "RegisterAccountCommand",
    "RecoverOwnerAccountCommand",
    "RecordAccountHeartbeatCommand",
    "ResetManagedAccountPasswordCommand",
    "SecurityPolicy",
    "SeedInitialOwnerCommand",
    "SeedInitialOwnerResult",
    "TemporaryPasswordResult",
    "ThemeKey",
    "UpdateAccountProfileCommand",
    "UpdateLandingPageCommand",
    "UpdateManagedAccountQuotaCommand",
    "UpdateThemeCommand",
    "UploadAvatarCommand",
)
