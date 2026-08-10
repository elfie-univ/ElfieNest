"""Typed models exchanged with capability Infrastructure Ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

CapabilityKey = Literal["web_search", "local_file"]
SearchProvider = Literal["duckduckgo", "brave", "tavily"]
ValidationStatus = Literal["passed", "failed", "warning", "skipped"]
WebSearchUpdateField = Literal[
    "enabled",
    "provider",
    "api_base",
    "max_results",
    "max_result_bytes",
]
LocalFileUpdateField = Literal["enabled", "max_read_bytes"]


@dataclass(frozen=True)
class StoredWebSearchCapability:
    enabled: bool
    provider: SearchProvider
    api_base: str
    credential_ref: str
    max_results: int
    max_result_bytes: int
    timeout_seconds: float
    max_tool_calls: int
    max_total_result_bytes: int


@dataclass(frozen=True)
class StoredLocalFileCapability:
    enabled: bool
    root: str
    root_policy: str
    max_read_bytes: int
    max_items: int
    max_result_bytes: int
    max_tool_calls: int
    max_total_result_bytes: int


@dataclass(frozen=True)
class StoredCapabilities:
    web_search: StoredWebSearchCapability
    local_file: StoredLocalFileCapability


@dataclass(frozen=True)
class StoredValidationResult:
    check_id: str
    status: ValidationStatus
    message: str
    duration_ms: Optional[float]
    provider: Optional[str]
    model: Optional[str]
    error_type: Optional[str]


__all__ = (
    "CapabilityKey",
    "LocalFileUpdateField",
    "SearchProvider",
    "StoredCapabilities",
    "StoredLocalFileCapability",
    "StoredValidationResult",
    "StoredWebSearchCapability",
    "ValidationStatus",
    "WebSearchUpdateField",
)
