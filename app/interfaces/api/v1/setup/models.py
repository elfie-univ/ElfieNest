"""Strict HTTP DTOs for first-run Setup resources."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.features.accounts import validate_password_strength
from app.features.setup import (
    SetupModelOptionResult,
    SetupOllamaResult,
    SetupOllamaState,
    SetupStatusResult,
)

_STRICT = ConfigDict(extra="forbid")


class SetupOwnerDraftRequest(BaseModel):
    model_config = _STRICT
    account_id: str = Field(min_length=3, max_length=32)
    display_name: Optional[str] = Field(default=None, max_length=64)
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    confirm_password: Optional[str] = Field(default=None, min_length=6, max_length=128)

    @field_validator("password", "confirm_password")
    @classmethod
    def strong_optional_password(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            validate_password_strength(value)
        return value

    @model_validator(mode="after")
    def passwords_match(self) -> SetupOwnerDraftRequest:
        if (self.password is None) != (self.confirm_password is None):
            raise ValueError("需要同时填写密码和确认密码")
        if self.password is not None and self.password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self


class SetupOfflineDraftRequest(BaseModel):
    model_config = _STRICT
    use_local_ollama: bool
    model_id: Optional[str] = Field(default=None, min_length=3, max_length=64)


class SetupNestDraftRequest(BaseModel):
    model_config = _STRICT
    bed_count: int = Field(strict=True)


class SetupInstallationRequest(BaseModel):
    model_config = _STRICT
    confirmed: Literal[True]


class SetupStepResponse(BaseModel):
    model_config = _STRICT
    number: int
    name: str
    status: Literal["pending", "current", "completed"]
    retry_action: Optional[str]


class SetupInstallResponse(BaseModel):
    model_config = _STRICT
    phase: Literal["owner", "ollama", "model", "emergency_food", "nest"]
    action_key: str
    state: Literal["idle", "running", "failed", "completed"]
    progress: int
    error_key: Optional[str]


class SetupDraftResponse(BaseModel):
    model_config = _STRICT
    owner_account_id: Optional[str]
    display_name: Optional[str]
    password_configured: bool
    use_local_ollama: Optional[bool]
    ollama_installed: bool
    model_id: Optional[str]
    bed_count: Optional[int]
    owner_configured: bool
    offline_configured: bool
    nest_configured: bool
    locked_at: Optional[str]


class SetupStatusResponse(BaseModel):
    model_config = _STRICT
    need_setup: bool
    complete: bool
    current_step: int
    steps: tuple[SetupStepResponse, ...]
    last_error: Optional[str]
    draft: SetupDraftResponse
    install: SetupInstallResponse
    locked: bool
    csrf_token: Optional[str] = None

    @classmethod
    def from_result(
        cls, result: SetupStatusResult, *, csrf_token: Optional[str] = None
    ) -> SetupStatusResponse:
        return cls(
            need_setup=result.need_setup,
            complete=result.complete,
            current_step=result.current_step,
            steps=tuple(SetupStepResponse(**item.__dict__) for item in result.steps),
            last_error=result.last_error,
            draft=SetupDraftResponse(**result.draft.__dict__),
            install=SetupInstallResponse(**result.install.__dict__),
            locked=result.locked,
            csrf_token=csrf_token,
        )


class SetupModelOptionResponse(BaseModel):
    model_config = _STRICT
    model_id: str
    label: str
    approx_download_mb: int
    recommended: bool

    @classmethod
    def from_result(cls, result: SetupModelOptionResult) -> SetupModelOptionResponse:
        return cls(**result.__dict__)


class SetupModelCollectionResponse(BaseModel):
    model_config = _STRICT
    items: tuple[SetupModelOptionResponse, ...]


class SetupOllamaResponse(BaseModel):
    model_config = _STRICT
    state: SetupOllamaState
    endpoint: Optional[str]
    version: Optional[str]
    platform: Literal["darwin", "linux", "win32"]

    @classmethod
    def from_result(cls, result: SetupOllamaResult) -> SetupOllamaResponse:
        return cls(**result.__dict__)


class SetupErrorDetails(BaseModel):
    model_config = _STRICT


class SetupErrorItem(BaseModel):
    model_config = _STRICT
    code: str
    message: str
    details: SetupErrorDetails


class SetupErrorResponse(BaseModel):
    model_config = _STRICT
    error: SetupErrorItem


__all__ = tuple(name for name in globals() if name.startswith("Setup"))
