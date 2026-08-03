"""Validated request and response models for the Setup API."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import TypeAlias

from app.features.accounts.password_policy import validate_password_strength
from app.features.setup.model_catalog import get_setup_model

_STRICT_MODEL = ConfigDict(extra="forbid", frozen=True)

SetupConfigStep: TypeAlias = Literal["owner", "offline", "nest", "review"]
SetupInstallPhase: TypeAlias = Literal[
    "owner", "ollama", "model", "emergency_food", "nest"
]


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


class SetupInstallStatus(BaseModel):
    model_config = _STRICT_MODEL

    phase: SetupInstallPhase
    action_key: str
    state: Literal["idle", "running", "failed", "completed"]
    progress: int = Field(..., ge=0, le=100)
    error_key: Optional[str] = None


class SetupModelOptionResponse(BaseModel):
    model_config = _STRICT_MODEL

    model_id: str
    label: str
    approx_download_mb: int
    recommended: bool


class SetupDraftView(BaseModel):
    model_config = _STRICT_MODEL

    owner_account_id: Optional[str] = None
    display_name: Optional[str] = None
    password_configured: bool = False
    use_local_ollama: Optional[bool] = None
    ollama_installed: bool = False
    model_id: Optional[str] = None
    bed_count: Optional[int] = None
    owner_configured: bool = False
    offline_configured: bool = False
    nest_configured: bool = False
    locked_at: Optional[str] = None


class SetupStatus(BaseModel):
    model_config = _STRICT_MODEL

    need_setup: bool
    complete: bool
    current_step: int
    steps: List[SetupStepStatus]
    last_error: Optional[str] = None
    task: Optional[SetupTaskStatus] = None
    draft: Optional[SetupDraftView] = None
    install: Optional[SetupInstallStatus] = None
    locked: bool = False
    csrf_token: Optional[str] = None


class SetupOwnerDraftRequest(BaseModel):
    model_config = _STRICT_MODEL

    account_id: str = Field(..., min_length=3, max_length=32)
    display_name: Optional[str] = Field(None, max_length=64)
    password: Optional[str] = Field(None, min_length=6, max_length=128)
    confirm_password: Optional[str] = Field(None, min_length=6, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else validate_password_strength(value)

    @field_validator("confirm_password")
    @classmethod
    def validate_confirmation(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else validate_password_strength(value)

    @model_validator(mode="after")
    def passwords_match(self) -> SetupOwnerDraftRequest:
        if (self.password is None) != (self.confirm_password is None):
            raise ValueError("需要同时填写密码和确认密码")
        if self.password is not None and self.password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self


class SetupOfflineDraftRequest(BaseModel):
    model_config = _STRICT_MODEL

    use_local_ollama: bool
    model_id: Optional[str] = Field(None, min_length=3, max_length=64)

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            get_setup_model(value)
        return value

    @model_validator(mode="after")
    def require_model_when_enabled(self) -> SetupOfflineDraftRequest:
        if self.use_local_ollama and self.model_id is None:
            raise ValueError("启用本地 Ollama 时必须选择模型")
        return self


class SetupNestDraftRequest(BaseModel):
    model_config = _STRICT_MODEL

    bed_count: int = Field(..., ge=4, le=32)


class SetupInstallRequest(BaseModel):
    model_config = _STRICT_MODEL

    confirmed: Literal[True]


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

    @field_validator("model_reference")
    @classmethod
    def validate_setup_model(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        get_setup_model(value)
        return value


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

    @field_validator("model_reference")
    @classmethod
    def validate_setup_model(cls, value: str) -> str:
        get_setup_model(value)
        return value
