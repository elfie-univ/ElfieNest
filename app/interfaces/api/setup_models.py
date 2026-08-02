"""Validated request and response models for the five-step Setup API."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.accounts.password_policy import validate_password_strength

_STRICT_MODEL = ConfigDict(extra="forbid", frozen=True)


class SetupStepStatus(BaseModel):
    model_config = _STRICT_MODEL

    number: int
    name: str
    status: str
    retry_action: Optional[str] = None


class SetupTaskStatus(BaseModel):
    model_config = _STRICT_MODEL

    step: int
    key: str
    state: str
    progress: int
    error: Optional[str] = None


class SetupStatus(BaseModel):
    model_config = _STRICT_MODEL

    need_setup: bool
    complete: bool
    current_step: int
    steps: List[SetupStepStatus]
    last_error: Optional[str] = None
    task: Optional[SetupTaskStatus] = None


class SetupRequest(BaseModel):
    model_config = _STRICT_MODEL

    account_id: str = Field(..., min_length=3, max_length=32)
    display_name: Optional[str] = Field(None, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    avatar_color: Optional[int] = Field(None, ge=0, le=7)

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value: str) -> str:
        """Require six effective characters after trimming outer whitespace."""
        return validate_password_strength(value)


class SetupOllamaRequest(BaseModel):
    model_config = _STRICT_MODEL

    decision: Literal["bound_existing", "skipped"]
    endpoint: Optional[str] = Field(None, min_length=1, max_length=256)


class SetupOllamaInstallRequest(BaseModel):
    model_config = _STRICT_MODEL

    confirmed: Literal[True]


class SetupNestRequest(BaseModel):
    model_config = _STRICT_MODEL

    bed_count: int = Field(..., ge=4, le=32)


class SetupModelRequest(BaseModel):
    model_config = _STRICT_MODEL

    decision: Literal["configured", "skipped"]
    model_reference: Optional[str] = Field(None, min_length=3, max_length=256)


SetupOllamaState = Literal[
    "absent",
    "healthy",
    "stopped",
    "deleted",
    "installing",
    "failed",
    "cancelled",
    "repair_required",
]


class SetupOllamaDetection(BaseModel):
    model_config = _STRICT_MODEL

    state: SetupOllamaState
    endpoint: Optional[str] = None
    version: Optional[str] = None


class SetupModelRecommendation(BaseModel):
    model_config = _STRICT_MODEL

    memory_gb: int
    recommended_model: Optional[str] = None
    ollama_state: SetupOllamaState
    ollama_endpoint: Optional[str] = None
    installed_models: List[str]
    recommended_model_available: bool


class SetupModelPullRequest(BaseModel):
    model_config = _STRICT_MODEL

    model_reference: str = Field(..., min_length=3, max_length=256)
    confirmed: Literal[True]
