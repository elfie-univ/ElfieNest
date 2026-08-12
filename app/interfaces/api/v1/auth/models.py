"""Strict HTTP DTOs for versioned authentication resources."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


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


__all__ = ("AuthUserResponse", "ErrorResponse", "LoginResponse", "LogoutResponse")
