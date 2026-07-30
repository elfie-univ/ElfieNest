"""Typed request contracts for Owner Provider management."""

from __future__ import annotations

from typing import List, Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

ApiMode = Literal["ollama", "chat_completions", "anthropic_messages"]
AuthType = Literal["none", "bearer", "x-api-key"]


class ProviderModelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(default="", max_length=200)
    canonical_model_id: Optional[str] = Field(default=None, max_length=200)
    context_window_tokens: Optional[int] = Field(default=None, gt=0)
    max_output_tokens: Optional[int] = Field(default=None, gt=0)
    supports_tools: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_reasoning: Optional[bool] = None

    @field_validator("id", "display_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("canonical_model_id")
    @classmethod
    def strip_optional_model_identity(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ProviderConnectionWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    alias: Optional[str] = Field(default=None, max_length=100)
    api_base: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=10_000)
    api_mode: Optional[ApiMode] = None
    auth_type: Optional[AuthType] = None
    models: Optional[List[ProviderModelInput]] = None
    verify: bool = True
    refresh_models: bool = False

    @field_validator("catalog_id", "alias", "api_base")
    @classmethod
    def strip_connection_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @field_validator("api_base")
    @classmethod
    def validate_connection_api_base(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        return ProviderWriteRequest.validate_api_base(value)


class ProviderConnectionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: Optional[str] = Field(default=None, max_length=100)
    api_base: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=10_000)
    api_mode: Optional[ApiMode] = None
    auth_type: Optional[AuthType] = None
    models: Optional[List[ProviderModelInput]] = None
    verify: bool = False
    refresh_models: bool = False

    @field_validator("alias", "api_base")
    @classmethod
    def strip_connection_update_text(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        return value.strip() if value is not None else None

    @field_validator("api_base")
    @classmethod
    def validate_connection_update_api_base(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        return ProviderWriteRequest.validate_api_base(value)


class ProviderModelUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = Field(default=None, max_length=200)
    canonical_model_id: Optional[str] = Field(default=None, max_length=200)
    context_window_tokens: Optional[int] = Field(default=None, gt=0)
    max_output_tokens: Optional[int] = Field(default=None, gt=0)
    supports_tools: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_reasoning: Optional[bool] = None
    hidden: Optional[bool] = None
    retired: Optional[bool] = None

    @field_validator("display_name", "canonical_model_id")
    @classmethod
    def strip_model_update_text(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ProviderWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Optional[str] = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    display_name: Optional[str] = Field(default=None, max_length=100)
    api_base: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=10_000)
    api_mode: Optional[ApiMode] = None
    auth_type: Optional[AuthType] = None
    test_model: Optional[str] = Field(default=None, max_length=200)
    models: Optional[List[ProviderModelInput]] = None
    refresh_models: bool = False

    @field_validator("provider_id", "display_name", "api_base", "test_model")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("API Base URL 必须是有效的 HTTP 或 HTTPS 地址")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("API Base URL 不得包含用户名或密码")
        return value


class VerifyBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_ids: List[str] = Field(default_factory=list, max_length=10)

    @field_validator("provider_ids")
    @classmethod
    def unique_provider_ids(cls, values: List[str]) -> List[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(set(normalized)) != len(normalized):
            raise ValueError("provider_ids 不能重复")
        return normalized


class BenchmarkCombination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=200)

    @field_validator("provider_id", "model_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class BenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    combinations: List[BenchmarkCombination] = Field(min_length=1, max_length=12)

    @field_validator("combinations")
    @classmethod
    def unique_combinations(
        cls, values: List[BenchmarkCombination]
    ) -> List[BenchmarkCombination]:
        keys = [(item.provider_id, item.model_id) for item in values]
        if len(set(keys)) != len(keys):
            raise ValueError("测速组合不能重复")
        return values


class ConnectionBenchmarkCombination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    model_id: str = Field(min_length=1, max_length=200)

    @field_validator("connection_id", "model_id")
    @classmethod
    def strip_connection_benchmark_text(cls, value: str) -> str:
        return value.strip()


class ConnectionBenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    combinations: List[ConnectionBenchmarkCombination] = Field(
        min_length=1,
        max_length=12,
    )

    @field_validator("combinations")
    @classmethod
    def unique_connection_combinations(
        cls,
        values: List[ConnectionBenchmarkCombination],
    ) -> List[ConnectionBenchmarkCombination]:
        keys = [(item.connection_id, item.model_id) for item in values]
        if len(set(keys)) != len(keys):
            raise ValueError("测速组合不能重复")
        return values
