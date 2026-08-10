"""Pydantic contracts for the Owner Ollama management card."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from infrastructure.models.ollama_platform import OllamaState


class OllamaOwnerTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: Literal["install", "model_pull"]
    state: Literal["running", "completed", "failed"]
    progress: int = Field(ge=0, le=100)
    error: Optional[str] = None


class OllamaOwnerModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    display_name: str
    installed: bool
    recommended: bool


class OllamaOwnerStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: OllamaState
    endpoint: Optional[str]
    version: Optional[str]
    memory_gb: int = Field(ge=0)
    recommended_model: Optional[str]
    installed_model_count: int = Field(ge=0)
    models: list[OllamaOwnerModelResponse]
    task: Optional[OllamaOwnerTaskResponse]


class OllamaInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    confirmed: Literal[True]


class OllamaPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_ids: list[str] = Field(min_length=1, max_length=8)
    confirmed: Literal[True]

    @field_validator("model_ids")
    @classmethod
    def normalize_model_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized or len(set(normalized)) != len(normalized):
            raise ValueError("模型清单不能为空且不能重复")
        return normalized
