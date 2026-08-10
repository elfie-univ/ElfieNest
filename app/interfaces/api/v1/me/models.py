"""Strict HTTP DTOs for the current-account resource."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.features.accounts import validate_password_strength

_STRICT = ConfigDict(extra="forbid", frozen=True)


class CurrentAccountResponse(BaseModel):
    model_config = _STRICT

    user_id: int
    account_id: str
    display_name: Optional[str]
    gender: Literal["male", "female"]
    birth_date: Optional[str]
    role: Literal["owner", "admin", "user"]
    avatar_url: Optional[str]
    avatar_color: int
    avatar_kind: Literal["initials", "emoji"]
    theme_key: Literal["warm-paper", "harbor-blue", "orchid-archive", "moss-green"]
    default_landing_page: Literal["chat", "manage"]
    created_at: str
    elfie_count: int
    csrf_token: str


class ProfileUpdateRequest(BaseModel):
    model_config = _STRICT

    account_id: Optional[StrictStr] = Field(default=None, min_length=3, max_length=32)
    display_name: Optional[StrictStr] = Field(default=None, max_length=64)
    gender: Optional[Literal["male", "female"]] = None
    birth_date: Optional[date] = None
    avatar_color: Optional[int] = Field(default=None, ge=0, le=7)
    avatar_kind: Optional[Literal["initials", "emoji"]] = None


class ProfileResponse(BaseModel):
    model_config = _STRICT

    user_id: int
    account_id: str
    display_name: Optional[str]
    gender: Literal["male", "female"]
    birth_date: Optional[str]
    avatar_url: Optional[str]
    avatar_color: int
    avatar_kind: Literal["initials", "emoji"]


class PasswordChangeRequest(BaseModel):
    model_config = _STRICT

    old_password: StrictStr
    new_password: StrictStr = Field(min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_strength(value)


class DetailResponse(BaseModel):
    model_config = _STRICT

    detail: str


class ThemePreferenceRequest(BaseModel):
    model_config = _STRICT

    theme_key: Literal["warm-paper", "harbor-blue", "orchid-archive", "moss-green"]


class ThemePreferenceResponse(BaseModel):
    model_config = _STRICT

    theme_key: Literal["warm-paper", "harbor-blue", "orchid-archive", "moss-green"]


class LandingPageRequest(BaseModel):
    model_config = _STRICT

    default_landing_page: Literal["chat", "manage"]


class LandingPageResponse(BaseModel):
    model_config = _STRICT

    default_landing_page: Literal["chat", "manage"]


class AvatarUploadResponse(BaseModel):
    model_config = _STRICT

    avatar_url: str


class AccountsErrorDetails(BaseModel):
    model_config = _STRICT


class AccountsErrorItem(BaseModel):
    model_config = _STRICT

    code: str
    message: str
    details: AccountsErrorDetails


class AccountsErrorResponse(BaseModel):
    model_config = _STRICT

    error: AccountsErrorItem


__all__ = (
    "AccountsErrorDetails",
    "AccountsErrorItem",
    "AccountsErrorResponse",
    "AvatarUploadResponse",
    "CurrentAccountResponse",
    "DetailResponse",
    "LandingPageRequest",
    "LandingPageResponse",
    "PasswordChangeRequest",
    "ProfileResponse",
    "ProfileUpdateRequest",
    "ThemePreferenceRequest",
    "ThemePreferenceResponse",
)
