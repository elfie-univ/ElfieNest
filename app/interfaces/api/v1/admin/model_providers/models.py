"""Strict HTTP DTOs for administrator model-Provider resources."""

from __future__ import annotations

from typing import List, Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.configuration import (
    ProviderBenchmarkRunResult,
    ProviderConnectionResult,
    ProviderConnectionVerificationResult,
    ProviderModelMatrixResult,
    ProviderModelRefreshResult,
    ProviderModelResult,
    ProviderOAuthLoginStartResult,
    ProviderOAuthLoginStatusResult,
    ProviderProductResult,
    ProviderValidationRunResult,
    ProviderVerificationResult,
)

StrictModel = ConfigDict(extra="forbid", strict=True)
ApiMode = Literal[
    "ollama", "chat_completions", "anthropic_messages", "codex_responses"
]
AuthType = Literal["none", "bearer", "x-api-key"]


class ProviderModelWriteRequest(BaseModel):
    model_config = StrictModel

    id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(default="", max_length=200)
    canonical_model_id: Optional[str] = Field(default=None, max_length=200)
    context_window_tokens: Optional[int] = Field(default=None, gt=0)
    max_output_tokens: Optional[int] = Field(default=None, gt=0)
    supports_tools: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_reasoning: Optional[bool] = None

    @field_validator("id")
    @classmethod
    def required_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("模型 ID 不能为空")
        return normalized

    @field_validator("display_name")
    @classmethod
    def display_name_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("canonical_model_id")
    @classmethod
    def optional_identity(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else value.strip() or None


class ProviderModelReplacementRequest(ProviderModelWriteRequest):
    original_id: str = Field(min_length=1, max_length=200)
    hidden: bool

    @field_validator("original_id")
    @classmethod
    def required_original_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("模型原始 ID 不能为空")
        return normalized


class ProviderModelsReplaceRequest(BaseModel):
    model_config = StrictModel

    models: List[ProviderModelReplacementRequest] = Field(max_length=200)


class ProviderModelPatchRequest(BaseModel):
    model_config = StrictModel

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
    def optional_text(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else value.strip() or None


class ProviderConnectionCreateRequest(BaseModel):
    model_config = StrictModel

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
    models: List[ProviderModelWriteRequest] = Field(
        default_factory=list,
        max_length=200,
    )
    verify: bool = False
    refresh_models: bool = False

    @field_validator("catalog_id", "alias", "api_base")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else value.strip()

    @field_validator("api_base")
    @classmethod
    def valid_api_base(cls, value: Optional[str]) -> Optional[str]:
        return _validate_api_base(value)


class ProviderConnectionPatchRequest(BaseModel):
    model_config = StrictModel

    alias: Optional[str] = Field(default=None, max_length=100)
    api_base: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=10_000)
    api_mode: Optional[ApiMode] = None
    auth_type: Optional[AuthType] = None
    models: Optional[List[ProviderModelWriteRequest]] = Field(
        default=None,
        max_length=200,
    )
    verify: bool = False
    refresh_models: bool = False

    @field_validator("alias", "api_base")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else value.strip()

    @field_validator("api_base")
    @classmethod
    def valid_api_base(cls, value: Optional[str]) -> Optional[str]:
        return _validate_api_base(value)


class ProviderOAuthLoginStartRequest(BaseModel):
    model_config = StrictModel

    catalog_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )


class ProviderOAuthLoginCompleteRequest(BaseModel):
    model_config = StrictModel

    catalog_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    alias: Optional[str] = Field(default=None, max_length=100)

    @field_validator("alias")
    @classmethod
    def strip_alias(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else value.strip() or None


class BenchmarkCombinationRequest(BaseModel):
    model_config = StrictModel

    connection_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    model_id: str = Field(min_length=1, max_length=200)


class BenchmarkModelsRequest(BaseModel):
    model_config = StrictModel

    combinations: List[BenchmarkCombinationRequest] = Field(
        min_length=1,
        max_length=12,
    )

    @field_validator("combinations")
    @classmethod
    def unique_combinations(
        cls,
        values: List[BenchmarkCombinationRequest],
    ) -> List[BenchmarkCombinationRequest]:
        keys = tuple((item.connection_id, item.model_id) for item in values)
        if len(set(keys)) != len(keys):
            raise ValueError("测速组合不能重复")
        return values


class ProviderBrandResponse(BaseModel):
    model_config = StrictModel
    brand_id: str
    name: str
    logo_asset: str


class ProviderProductResponse(BaseModel):
    model_config = StrictModel
    catalog_id: str
    name: str
    brand: ProviderBrandResponse
    connection_method: Literal["local", "api_key", "oauth"]
    oauth_available: bool
    usage_scope: str
    discovery_strategy: str
    api_mode: ApiMode

    @classmethod
    def from_result(cls, item: ProviderProductResult) -> ProviderProductResponse:
        return cls(
            catalog_id=item.catalog_id,
            name=item.name,
            brand=ProviderBrandResponse(**vars(item.brand)),
            connection_method=item.connection_method,
            oauth_available=item.oauth_available,
            usage_scope=item.usage_scope,
            discovery_strategy=item.discovery_strategy,
            api_mode=item.api_mode,
        )


class ProviderProductsResponse(BaseModel):
    model_config = StrictModel
    items: tuple[ProviderProductResponse, ...]


class ProviderVerificationResponse(BaseModel):
    model_config = StrictModel
    status: Literal["never", "passed", "failed"]
    checked_at: Optional[str]
    latency_ms: Optional[float]
    error: Optional[str]
    validation_mode: Literal["none", "full", "cached", "heartbeat", "benchmark"]
    cache_hit: bool
    needs_full_validation: bool
    needs_heartbeat: bool
    full_run_id: Optional[str]
    full_checked_at: Optional[str]
    heartbeat_checked_at: Optional[str]
    heartbeat_status: Optional[Literal["passed", "failed"]]
    representative_model_id: Optional[str]
    reason: Optional[str]

    @classmethod
    def from_result(
        cls,
        item: ProviderVerificationResult,
    ) -> ProviderVerificationResponse:
        return cls(**vars(item))


class ProviderModelResponse(BaseModel):
    model_config = StrictModel
    id: str
    display_name: str
    canonical_model_id: Optional[str]
    source: Literal["official", "remote_catalog", "bundled_catalog", "manual"]
    context_window_tokens: Optional[int]
    max_output_tokens: Optional[int]
    supports_tools: Optional[bool]
    supports_vision: Optional[bool]
    supports_reasoning: Optional[bool]
    hidden: bool
    retired: bool
    available: bool
    verification: ProviderVerificationResponse

    @classmethod
    def from_result(cls, item: ProviderModelResult) -> ProviderModelResponse:
        return cls(
            id=item.model_id,
            display_name=item.display_name,
            canonical_model_id=item.canonical_model_id,
            source=item.source,
            context_window_tokens=item.context_window_tokens,
            max_output_tokens=item.max_output_tokens,
            supports_tools=item.supports_tools,
            supports_vision=item.supports_vision,
            supports_reasoning=item.supports_reasoning,
            hidden=item.hidden,
            retired=item.retired,
            available=item.available,
            verification=ProviderVerificationResponse.from_result(item.verification),
        )


class ModelRefreshResponse(BaseModel):
    model_config = StrictModel
    status: str
    checked_at: str
    message: Optional[str]
    models: tuple[ProviderModelResponse, ...]

    @classmethod
    def from_result(cls, item: ProviderModelRefreshResult) -> ModelRefreshResponse:
        return cls(
            status=item.status,
            checked_at=item.checked_at,
            message=item.message,
            models=tuple(
                ProviderModelResponse.from_result(model) for model in item.models
            ),
        )


class ProviderConnectionResponse(BaseModel):
    model_config = StrictModel
    connection_id: str
    catalog_id: str
    alias: str
    api_base: str
    api_mode: ApiMode
    auth_type: AuthType
    has_api_key: bool
    has_credential: bool
    enabled: bool
    archived: bool
    usage_scope: str
    verification: ProviderVerificationResponse
    models: tuple[ProviderModelResponse, ...]
    model_refresh: Optional[ModelRefreshResponse]

    @classmethod
    def from_result(
        cls,
        item: ProviderConnectionResult,
    ) -> ProviderConnectionResponse:
        return cls(
            connection_id=item.connection_id,
            catalog_id=item.catalog_id,
            alias=item.alias,
            api_base=item.api_base,
            api_mode=item.api_mode,
            auth_type=item.auth_type,
            has_api_key=item.has_api_key,
            has_credential=item.has_credential,
            enabled=item.enabled,
            archived=item.archived,
            usage_scope=item.usage_scope,
            verification=ProviderVerificationResponse.from_result(item.verification),
            models=tuple(
                ProviderModelResponse.from_result(model) for model in item.models
            ),
            model_refresh=(
                None
                if item.model_refresh is None
                else ModelRefreshResponse.from_result(item.model_refresh)
            ),
        )


class ProviderConnectionsResponse(BaseModel):
    model_config = StrictModel
    items: tuple[ProviderConnectionResponse, ...]


class ProviderOAuthLoginStartResponse(BaseModel):
    model_config = StrictModel
    catalog_id: str
    login_id: str
    authorization_url: str
    user_code: str
    poll_interval_seconds: int
    expires_at: str

    @classmethod
    def from_result(
        cls, item: ProviderOAuthLoginStartResult
    ) -> ProviderOAuthLoginStartResponse:
        return cls(**vars(item))


class ProviderOAuthLoginStatusResponse(BaseModel):
    model_config = StrictModel
    catalog_id: str
    login_id: str
    state: Literal["pending", "completed"]
    account_id: Optional[str]
    expires_at: Optional[str]
    connection: Optional[ProviderConnectionResponse]

    @classmethod
    def from_result(
        cls, item: ProviderOAuthLoginStatusResult
    ) -> ProviderOAuthLoginStatusResponse:
        return cls(
            catalog_id=item.catalog_id,
            login_id=item.login_id,
            state=item.state,
            account_id=item.account_id,
            expires_at=item.expires_at,
            connection=(
                None
                if item.connection is None
                else ProviderConnectionResponse.from_result(item.connection)
            ),
        )


class LocalProviderTaskResponse(BaseModel):
    model_config = StrictModel

    key: Literal["install", "model_pull"]
    state: Literal["running", "completed", "failed"]
    progress: int = Field(ge=0, le=100)
    error: Optional[str]


class LocalProviderModelResponse(BaseModel):
    model_config = StrictModel

    id: str
    display_name: str
    installed: bool
    recommended: bool


class LocalProviderStatusResponse(BaseModel):
    model_config = StrictModel

    state: Literal[
        "absent",
        "healthy",
        "stopped",
        "deleted",
        "installing",
        "failed",
        "cancelled",
        "repair_required",
    ]
    endpoint: Optional[str]
    version: Optional[str]
    memory_gb: int = Field(ge=0)
    recommended_model: Optional[str]
    installed_model_count: int = Field(ge=0)
    models: tuple[LocalProviderModelResponse, ...]
    task: Optional[LocalProviderTaskResponse]


class LocalProviderInstallRequest(BaseModel):
    model_config = StrictModel

    confirmed: Literal[True]


class LocalProviderPullRequest(BaseModel):
    model_config = StrictModel

    model_ids: List[str] = Field(min_length=1, max_length=8)
    confirmed: Literal[True]

    @field_validator("model_ids")
    @classmethod
    def normalized_model_ids(cls, values: List[str]) -> List[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized or len(set(normalized)) != len(normalized):
            raise ValueError("模型清单不能为空且不能重复")
        return normalized


class VerifyConnectionResponse(BaseModel):
    model_config = StrictModel
    connection_id: str
    verification: ProviderVerificationResponse

    @classmethod
    def from_result(
        cls,
        item: ProviderConnectionVerificationResult,
    ) -> VerifyConnectionResponse:
        return cls(
            connection_id=item.connection_id,
            verification=ProviderVerificationResponse.from_result(item.verification),
        )


class DetailResponse(BaseModel):
    model_config = StrictModel
    detail: str


class MatrixSnapshotResponse(BaseModel):
    model_config = StrictModel
    mode: str
    run_id: Optional[str]
    as_of: Optional[str]
    status: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]


class MatrixCellResponse(BaseModel):
    model_config = StrictModel
    connection_id: str
    model_id: Optional[str]
    available: bool
    verification_status: Literal["never", "passed", "failed"]
    benchmark_status: Optional[Literal["passed", "failed"]]
    latency_ms: Optional[float]
    latency_class: Optional[Literal["fast", "normal", "slow"]]
    price_estimate: Optional[float]


class MatrixConnectionResponse(BaseModel):
    model_config = StrictModel
    connection_id: str
    name: str
    verification: ProviderVerificationResponse


class MatrixModelResponse(BaseModel):
    model_config = StrictModel
    model_key: str
    display_name: str
    capabilities: tuple[str, ...]
    connections: tuple[MatrixCellResponse, ...]


class ModelMatrixResponse(BaseModel):
    model_config = StrictModel
    snapshot: MatrixSnapshotResponse
    connections: tuple[MatrixConnectionResponse, ...]
    models: tuple[MatrixModelResponse, ...]

    @classmethod
    def from_result(cls, item: ProviderModelMatrixResult) -> ModelMatrixResponse:
        return cls(
            snapshot=MatrixSnapshotResponse(**vars(item.snapshot)),
            connections=tuple(
                MatrixConnectionResponse(
                    connection_id=value.connection_id,
                    name=value.name,
                    verification=ProviderVerificationResponse.from_result(
                        value.verification
                    ),
                )
                for value in item.connections
            ),
            models=tuple(
                MatrixModelResponse(
                    model_key=value.model_key,
                    display_name=value.display_name,
                    capabilities=value.capabilities,
                    connections=tuple(
                        MatrixCellResponse(**vars(cell)) for cell in value.connections
                    ),
                )
                for value in item.models
            ),
        )


class BenchmarkResultResponse(BaseModel):
    model_config = StrictModel
    connection_id: str
    model_id: str
    status: Literal["passed", "failed"]
    checked_at: str
    latency_ms: Optional[float]
    latency_class: Optional[Literal["fast", "normal", "slow"]]
    error: Optional[str]


class BenchmarkRunResponse(BaseModel):
    model_config = StrictModel
    run_id: str
    status: str
    results: tuple[BenchmarkResultResponse, ...]

    @classmethod
    def from_result(cls, item: ProviderBenchmarkRunResult) -> BenchmarkRunResponse:
        return cls(
            run_id=item.run_id,
            status=item.status,
            results=tuple(
                BenchmarkResultResponse(**vars(value)) for value in item.results
            ),
        )


class ValidationItemResponse(BaseModel):
    model_config = StrictModel
    subject: str
    status: str
    checked_at: Optional[str]


class ValidationRunResponse(BaseModel):
    model_config = StrictModel
    run_id: str
    status: str
    results: tuple[ValidationItemResponse, ...]

    @classmethod
    def from_result(cls, item: ProviderValidationRunResult) -> ValidationRunResponse:
        return cls(
            run_id=item.run_id,
            status=item.status,
            results=tuple(
                ValidationItemResponse(**vars(value)) for value in item.results
            ),
        )


class ErrorDetails(BaseModel):
    model_config = StrictModel


class ErrorItem(BaseModel):
    model_config = StrictModel
    code: str
    message: str
    details: ErrorDetails


class ErrorResponse(BaseModel):
    model_config = StrictModel
    error: ErrorItem


def _validate_api_base(value: Optional[str]) -> Optional[str]:
    if value in {None, ""}:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("API Base URL 必须是有效的 HTTP 或 HTTPS 地址")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("API Base URL 不得包含用户名或密码")
    return value


__all__ = tuple(name for name in globals() if name.endswith(("Request", "Response")))
