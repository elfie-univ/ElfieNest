"""Strict HTTP DTOs for versioned global Settings resources."""

from __future__ import annotations

from typing import Mapping, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    model_validator,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _PatchModel(_StrictModel):
    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if isinstance(value, Mapping):
            null_fields = [key for key, item in value.items() if item is None]
            if null_fields:
                raise ValueError(
                    f"设置字段不能为 null: {', '.join(sorted(map(str, null_fields)))}"
                )
        return value


class ElfieSettingsPatch(_PatchModel):
    max_elfies_per_user: Optional[StrictInt] = Field(
        default=None,
        ge=1,
        le=32,
    )
    personality_presets_enabled: Optional[dict[str, StrictBool]] = None


class RuntimeSettingsPatch(_PatchModel):
    tick_interval_sec: Optional[Union[StrictFloat, StrictInt]] = Field(
        default=None,
        gt=0,
    )


class LoginRateLimitRequest(_StrictModel):
    max_attempts: StrictInt = Field(ge=1)
    window_seconds: StrictInt = Field(ge=1)


class SecuritySettingsPatch(_PatchModel):
    session_ttl_days: Optional[StrictInt] = Field(default=None, ge=1)
    rate_limit: Optional[LoginRateLimitRequest] = None


class ElfieSettingsResponse(_StrictModel):
    max_elfies_per_user: int
    personality_presets_enabled: dict[str, bool]


class RuntimeSettingsResponse(_StrictModel):
    tick_interval_sec: float


class LoginRateLimitResponse(_StrictModel):
    max_attempts: int
    window_seconds: int


class SecuritySettingsResponse(_StrictModel):
    session_ttl_days: int
    rate_limit: LoginRateLimitResponse


class ErrorBody(_StrictModel):
    code: str
    message: str


class ErrorResponse(_StrictModel):
    error: ErrorBody


__all__ = (
    "ElfieSettingsPatch",
    "ElfieSettingsResponse",
    "ErrorResponse",
    "LoginRateLimitRequest",
    "LoginRateLimitResponse",
    "RuntimeSettingsPatch",
    "RuntimeSettingsResponse",
    "SecuritySettingsPatch",
    "SecuritySettingsResponse",
)
