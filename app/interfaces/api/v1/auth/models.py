"""Strict HTTP DTOs for versioned authentication resources."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.features.accounts import validate_password_strength


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: int
    account_id: str
    display_name: Optional[str]
    role: Literal["owner", "admin", "user"]
    default_landing_page: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user: AuthUserResponse
    csrf_token: str
    landing_path: Literal["/chat", "/manage", "/monitor"]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: StrictStr = Field(min_length=1, max_length=64)
    account_id: StrictStr = Field(min_length=3, max_length=32)
    password: StrictStr = Field(min_length=6, max_length=128)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("显示名称不能为空")
        return normalized

    @field_validator("account_id")
    @classmethod
    def normalize_account_id(cls, value: str) -> str:
        normalized = value.strip()
        if not 3 <= len(normalized) <= 32:
            raise ValueError("登录账号去除首尾空格后必须为 3-32 个字符")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class LogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    detail: Literal["已登出"]


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ErrorBody


__all__ = (
    "AuthUserResponse",
    "ErrorResponse",
    "LoginResponse",
    "LogoutResponse",
    "RegisterRequest",
)
