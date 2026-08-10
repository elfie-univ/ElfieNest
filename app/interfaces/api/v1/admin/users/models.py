"""Strict HTTP DTOs for administrator user resources."""

from __future__ import annotations

from typing import Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.features.accounts import validate_password_strength

_STRICT = ConfigDict(extra="forbid", frozen=True)


class ManagedUserResponse(BaseModel):
    model_config = _STRICT

    user_id: int
    account_id: str
    display_name: Optional[str]
    role: Literal["owner", "admin", "user"]
    gender: Literal["male", "female"]
    birth_date: Optional[str]
    presence: Literal["online", "away", "offline"]
    last_seen_at: Optional[str]
    language: str
    created_at: str
    elfie_count: int
    elfie_quota_override: Optional[int]
    effective_elfie_limit: int
    avatar_url: Optional[str]


class ManagedUsersResponse(BaseModel):
    model_config = _STRICT

    items: Tuple[ManagedUserResponse, ...]


class CreateManagedUserRequest(BaseModel):
    model_config = _STRICT

    account_id: StrictStr = Field(min_length=3, max_length=32)
    display_name: Optional[StrictStr] = Field(default=None, max_length=64)
    password: StrictStr = Field(min_length=6, max_length=128)
    role: Literal["admin", "user"]

    @field_validator("account_id")
    @classmethod
    def normalize_account_id(cls, value: str) -> str:
        normalized = value.strip()
        if not 3 <= len(normalized) <= 32:
            raise ValueError("登录账号去除首尾空格后必须为 3-32 个字符")
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class UpdateManagedUserRequest(BaseModel):
    model_config = _STRICT

    elfie_quota_override: Optional[int] = Field(default=None, ge=1, le=32)


class TemporaryPasswordResponse(BaseModel):
    model_config = _STRICT

    temporary_password: str


class AdminUsersErrorDetails(BaseModel):
    model_config = _STRICT


class AdminUsersErrorItem(BaseModel):
    model_config = _STRICT

    code: str
    message: str
    details: AdminUsersErrorDetails


class AdminUsersErrorResponse(BaseModel):
    model_config = _STRICT

    error: AdminUsersErrorItem


__all__ = (
    "AdminUsersErrorDetails",
    "AdminUsersErrorItem",
    "AdminUsersErrorResponse",
    "CreateManagedUserRequest",
    "ManagedUserResponse",
    "ManagedUsersResponse",
    "TemporaryPasswordResponse",
    "UpdateManagedUserRequest",
)
