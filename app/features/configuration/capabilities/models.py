"""Commands, queries and results owned by capability administration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional

from .port_models import (
    CapabilityKey,
    LocalFileUpdateField,
    SearchProvider,
    ValidationStatus,
    WebSearchUpdateField,
)


@dataclass(frozen=True)
class ListCapabilitiesQuery:
    pass


@dataclass(frozen=True)
class UpdateWebSearchCapabilityCommand:
    fields: FrozenSet[WebSearchUpdateField]
    enabled: Optional[bool] = None
    provider: Optional[SearchProvider] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    max_results: Optional[int] = None
    max_result_bytes: Optional[int] = None


@dataclass(frozen=True)
class UpdateLocalFileCapabilityCommand:
    fields: FrozenSet[LocalFileUpdateField]
    enabled: Optional[bool] = None
    max_read_bytes: Optional[int] = None


@dataclass(frozen=True)
class VerifyCapabilityCommand:
    capability_key: CapabilityKey


@dataclass(frozen=True)
class WebSearchCapabilityResult:
    enabled: bool
    provider: SearchProvider
    api_base: str
    max_results: int
    max_result_bytes: int
    timeout_seconds: float
    max_tool_calls: int
    max_total_result_bytes: int
    has_api_key: bool


@dataclass(frozen=True)
class LocalFileCapabilityResult:
    enabled: bool
    root: str
    root_policy: str
    max_read_bytes: int
    max_items: int
    max_result_bytes: int
    max_tool_calls: int
    max_total_result_bytes: int
    has_api_key: bool


@dataclass(frozen=True)
class CapabilitiesResult:
    web_search: WebSearchCapabilityResult
    local_file: LocalFileCapabilityResult


@dataclass(frozen=True)
class CapabilityValidationResult:
    check_id: str
    status: ValidationStatus
    message: str
    duration_ms: Optional[float]
    provider: Optional[str]
    model: Optional[str]
    error_type: Optional[str]


@dataclass(frozen=True)
class CapabilityValidationSummary:
    passed: int
    failed: int
    warning: int
    skipped: int


@dataclass(frozen=True)
class CapabilityValidationSuiteResult:
    name: str
    passed: bool
    summary: CapabilityValidationSummary
    results: tuple[CapabilityValidationResult, ...]


__all__ = (
    "CapabilitiesResult",
    "CapabilityValidationResult",
    "CapabilityValidationSuiteResult",
    "CapabilityValidationSummary",
    "ListCapabilitiesQuery",
    "LocalFileCapabilityResult",
    "UpdateLocalFileCapabilityCommand",
    "UpdateWebSearchCapabilityCommand",
    "VerifyCapabilityCommand",
    "WebSearchCapabilityResult",
)
