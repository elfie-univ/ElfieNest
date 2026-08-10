"""Strict HTTP DTOs for administrator capability settings."""

from __future__ import annotations

from typing import Literal, Mapping, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.features.configuration import (
    CapabilityValidationSuiteResult,
    LocalFileCapabilityResult,
    WebSearchCapabilityResult,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _PatchModel(_StrictModel):
    @model_validator(mode="before")
    @classmethod
    def reject_null_and_empty(cls, value: object) -> object:
        if isinstance(value, Mapping):
            if not value:
                raise ValueError("至少需要更新一个字段")
            null_fields = [key for key, item in value.items() if item is None]
            if null_fields:
                raise ValueError(
                    f"能力字段不能为 null: {', '.join(sorted(map(str, null_fields)))}"
                )
        return value


class WebSearchCapabilityPatch(_PatchModel):
    enabled: Optional[StrictBool] = None
    provider: Optional[Literal["duckduckgo", "brave", "tavily"]] = None
    api_base: Optional[StrictStr] = None
    api_key: Optional[StrictStr] = None
    max_results: Optional[StrictInt] = None
    max_result_bytes: Optional[StrictInt] = None


class LocalFileCapabilityPatch(_PatchModel):
    enabled: Optional[StrictBool] = None
    max_read_bytes: Optional[StrictInt] = None


class WebSearchCapabilityResponse(_StrictModel):
    enabled: bool
    provider: Literal["duckduckgo", "brave", "tavily"]
    api_base: str
    max_results: int
    max_result_bytes: int
    timeout_seconds: float
    max_tool_calls: int
    max_total_result_bytes: int
    has_api_key: bool

    @classmethod
    def from_result(
        cls, result: WebSearchCapabilityResult
    ) -> WebSearchCapabilityResponse:
        return cls(
            enabled=result.enabled,
            provider=result.provider,
            api_base=result.api_base,
            max_results=result.max_results,
            max_result_bytes=result.max_result_bytes,
            timeout_seconds=result.timeout_seconds,
            max_tool_calls=result.max_tool_calls,
            max_total_result_bytes=result.max_total_result_bytes,
            has_api_key=result.has_api_key,
        )


class LocalFileCapabilityResponse(_StrictModel):
    enabled: bool
    root: str
    root_policy: str
    max_read_bytes: int
    max_items: int
    max_result_bytes: int
    max_tool_calls: int
    max_total_result_bytes: int
    has_api_key: bool

    @classmethod
    def from_result(
        cls, result: LocalFileCapabilityResult
    ) -> LocalFileCapabilityResponse:
        return cls(
            enabled=result.enabled,
            root=result.root,
            root_policy=result.root_policy,
            max_read_bytes=result.max_read_bytes,
            max_items=result.max_items,
            max_result_bytes=result.max_result_bytes,
            max_tool_calls=result.max_tool_calls,
            max_total_result_bytes=result.max_total_result_bytes,
            has_api_key=result.has_api_key,
        )


class CapabilityConfigurationResponse(_StrictModel):
    web_search: WebSearchCapabilityResponse
    local_file: LocalFileCapabilityResponse


class CapabilitiesResponse(_StrictModel):
    tools: CapabilityConfigurationResponse


class WebSearchCapabilityUpdateResponse(_StrictModel):
    tool_key: Literal["web_search"]
    config: WebSearchCapabilityResponse


class LocalFileCapabilityUpdateResponse(_StrictModel):
    tool_key: Literal["local_file"]
    config: LocalFileCapabilityResponse


class CapabilityValidationDetails(_StrictModel):
    error_type: Optional[str] = None


class CapabilityValidationCheckResponse(_StrictModel):
    check_id: str
    status: Literal["passed", "failed", "warning", "skipped"]
    message: str
    duration_ms: Optional[float]
    provider: Optional[str]
    model: Optional[str]
    details: CapabilityValidationDetails


class CapabilityValidationSummaryResponse(_StrictModel):
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    warning: int = Field(ge=0)
    skipped: int = Field(ge=0)


class CapabilityValidationSuiteResponse(_StrictModel):
    name: str
    passed: bool
    summary: CapabilityValidationSummaryResponse
    results: tuple[CapabilityValidationCheckResponse, ...]

    @classmethod
    def from_result(
        cls, result: CapabilityValidationSuiteResult
    ) -> CapabilityValidationSuiteResponse:
        return cls(
            name=result.name,
            passed=result.passed,
            summary=CapabilityValidationSummaryResponse(
                passed=result.summary.passed,
                failed=result.summary.failed,
                warning=result.summary.warning,
                skipped=result.summary.skipped,
            ),
            results=tuple(
                CapabilityValidationCheckResponse(
                    check_id=item.check_id,
                    status=item.status,
                    message=item.message,
                    duration_ms=item.duration_ms,
                    provider=item.provider,
                    model=item.model,
                    details=CapabilityValidationDetails(error_type=item.error_type),
                )
                for item in result.results
            ),
        )


class CapabilityErrorDetails(_StrictModel):
    pass


class CapabilityErrorItem(_StrictModel):
    code: str
    message: str
    details: CapabilityErrorDetails


class CapabilityErrorResponse(_StrictModel):
    error: CapabilityErrorItem


__all__ = (
    "CapabilitiesResponse",
    "CapabilityConfigurationResponse",
    "CapabilityErrorDetails",
    "CapabilityErrorItem",
    "CapabilityErrorResponse",
    "CapabilityValidationSuiteResponse",
    "LocalFileCapabilityPatch",
    "LocalFileCapabilityResponse",
    "LocalFileCapabilityUpdateResponse",
    "WebSearchCapabilityPatch",
    "WebSearchCapabilityResponse",
    "WebSearchCapabilityUpdateResponse",
)
