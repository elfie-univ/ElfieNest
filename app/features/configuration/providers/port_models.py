"""Strict models crossing Providers-owned technical Ports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

ApiMode = Literal["ollama", "chat_completions", "anthropic_messages", "codex_responses"]
AuthType = Literal["none", "bearer", "x-api-key"]
ConnectionMethod = Literal["local", "api_key", "oauth"]
DiscoveryStrategy = Literal[
    "catalog_only", "ollama", "provider_adapter", "standard_models"
]
ModelSource = Literal["official", "remote_catalog", "bundled_catalog", "manual"]
DiscoveryState = Literal["present", "source_missing"]
ValidationMode = Literal["none", "full", "cached", "heartbeat", "benchmark"]
ValidationStatus = Literal["never", "passed", "failed"]
AvailabilityStatus = Literal["available", "degraded", "unavailable", "unknown"]
ProviderAvailabilityStatus = Literal[
    "healthy", "degraded", "unavailable", "unknown", "disabled"
]
CapabilityState = Literal["supported", "unsupported", "unknown"]
CapabilityEvidence = Literal[
    "declared", "declared_by_user", "accepted", "verified", "unknown"
]
CapabilityName = Literal["tools", "vision", "reasoning", "structured_output"]
LatencyClass = Literal["fast", "normal", "slow"]
LocalProviderState = Literal[
    "absent",
    "healthy",
    "stopped",
    "deleted",
    "installing",
    "failed",
    "cancelled",
    "repair_required",
]
LocalPlatformName = Literal["darwin", "linux", "win32"]


@dataclass(frozen=True)
class StoredProviderBrand:
    brand_id: str
    name: str
    logo_asset: str


@dataclass(frozen=True)
class StoredProviderProduct:
    catalog_id: str
    name: str
    brand: StoredProviderBrand
    connection_method: ConnectionMethod
    oauth_available: bool
    usage_scope: str
    discovery_strategy: DiscoveryStrategy
    api_mode: ApiMode
    api_base: str
    auth_type: AuthType


@dataclass(frozen=True)
class StoredProviderModel:
    model_id: str
    display_name: str
    canonical_model_id: str | None = None
    source: ModelSource = "manual"
    request_profile_id: str | None = None
    request_profile_version: int | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    supports_reasoning: bool | None = None
    supports_structured_output: bool | None = None
    capability_evidence: Mapping[str, CapabilityEvidence] = field(default_factory=dict)
    hidden: bool = False
    retired: bool = False
    available: bool = True
    discovery_state: DiscoveryState = "present"
    consecutive_missing: int = 0
    last_seen_at: str | None = None


@dataclass(frozen=True)
class StoredProviderConnection:
    connection_id: str
    catalog_id: str
    alias: str
    api_base: str
    api_mode: ApiMode
    auth_type: AuthType
    credential_ref: str
    models: tuple[StoredProviderModel, ...]
    enabled: bool = True
    archived: bool = False


@dataclass(frozen=True)
class StoredProviderOAuthLoginStart:
    catalog_id: str
    login_id: str
    authorization_url: str
    user_code: str
    poll_interval_seconds: int
    expires_at: str


@dataclass(frozen=True)
class StoredProviderOAuthLoginStatus:
    catalog_id: str
    login_id: str
    state: Literal["pending", "completed"]
    credential_ref: str = ""
    account_id: str | None = None
    expires_at: str | None = None


@dataclass(frozen=True)
class StoredLocalProviderBinding:
    api_base: str
    platform: LocalPlatformName
    install_kind: str
    launch_target: str
    version: str = ""
    installer_source_url: str = ""
    installer_sha256: str = ""


@dataclass(frozen=True)
class StoredLocalProviderProbe:
    state: LocalProviderState
    endpoint: str
    version: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class StoredLocalProviderCandidate:
    model_id: str
    display_name: str
    recommended: bool


@dataclass(frozen=True)
class StoredVerification:
    status: ValidationStatus = "never"
    checked_at: str | None = None
    latency_ms: float | None = None
    error: str | None = None
    validation_mode: ValidationMode = "none"
    cache_hit: bool = False
    needs_full_validation: bool = False
    needs_heartbeat: bool = False
    full_run_id: str | None = None
    full_checked_at: str | None = None
    heartbeat_checked_at: str | None = None
    heartbeat_status: Literal["passed", "failed"] | None = None
    representative_model_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class StoredModelVerification:
    status: ValidationStatus = "never"
    checked_at: str | None = None
    latency_ms: float | None = None
    error: str | None = None
    validation_mode: ValidationMode | None = None
    full_run_id: str | None = None
    availability_status: Literal["available", "degraded", "unavailable", "unknown"] = (
        "unknown"
    )
    reason_code: str | None = None
    evidence_source: str | None = None
    expires_at: str | None = None
    is_core: bool = False


@dataclass(frozen=True)
class StoredCapabilityProbeResult:
    capability: CapabilityName
    state: CapabilityState
    evidence: CapabilityEvidence
    status: Literal["passed", "failed"]
    latency_ms: float
    error: str | None = None
    error_code: str | None = None
    error_scope: str | None = None
    error_category: str | None = None


@dataclass(frozen=True)
class StoredObsoleteModel:
    model: StoredProviderModel
    eligible: bool
    reason: str
    last_production_at: str | None = None


@dataclass(frozen=True)
class StoredEndpointCapability:
    name: Literal["tools", "vision", "reasoning", "structured_output"]
    state: CapabilityState
    evidence: CapabilityEvidence


@dataclass(frozen=True)
class StoredModelAvailability:
    reference: str
    connection_id: str
    model_id: str
    status: AvailabilityStatus
    reason_code: str | None
    provider_status: ProviderAvailabilityStatus
    evidence_source: str | None
    observed_at: str | None
    expires_at: str | None
    is_core: bool
    serving_food_ids: tuple[str, ...]
    serving_roles: tuple[str, ...]
    capabilities: tuple[StoredEndpointCapability, ...]
    reachability_status: AvailabilityStatus = "unknown"
    reachability_observed_at: str | None = None
    reachability_expires_at: str | None = None


@dataclass(frozen=True)
class StoredModelRefresh:
    status: str
    checked_at: str
    message: str | None
    models: tuple[StoredProviderModel, ...]
    # Retained inventory is persisted even when source_missing models are
    # hidden from the normal model list.
    persisted_models: tuple[StoredProviderModel, ...] | None = None


@dataclass(frozen=True)
class StoredMatrixCell:
    connection_id: str
    model_id: str | None
    available: bool
    verification_status: ValidationStatus
    benchmark_status: Literal["passed", "failed"] | None
    latency_ms: float | None
    latency_class: LatencyClass | None
    price_estimate: float | None


@dataclass(frozen=True)
class StoredMatrixModel:
    model_key: str
    display_name: str
    capabilities: tuple[str, ...]
    connections: tuple[StoredMatrixCell, ...]


@dataclass(frozen=True)
class StoredMatrixConnection:
    connection_id: str
    name: str
    verification: StoredVerification


@dataclass(frozen=True)
class StoredMatrixSnapshot:
    mode: str
    run_id: str | None = None
    as_of: str | None = None
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class StoredModelMatrix:
    snapshot: StoredMatrixSnapshot
    connections: tuple[StoredMatrixConnection, ...]
    models: tuple[StoredMatrixModel, ...]


@dataclass(frozen=True)
class StoredBenchmarkCombination:
    connection_id: str
    model_id: str


@dataclass(frozen=True)
class StoredBenchmarkResult:
    connection_id: str
    model_id: str
    status: Literal["passed", "failed"]
    checked_at: str
    latency_ms: float | None
    latency_class: LatencyClass | None
    error: str | None


@dataclass(frozen=True)
class StoredBenchmarkRun:
    run_id: str
    status: str
    results: tuple[StoredBenchmarkResult, ...]


@dataclass(frozen=True)
class StoredValidationItem:
    subject: str
    status: str
    checked_at: str | None = None


@dataclass(frozen=True)
class StoredValidationRun:
    run_id: str
    status: str
    results: tuple[StoredValidationItem, ...]


__all__ = tuple(name for name in globals() if name.startswith("Stored")) + (
    "ApiMode",
    "AuthType",
    "ConnectionMethod",
    "DiscoveryStrategy",
    "LatencyClass",
    "ModelSource",
    "ValidationMode",
    "ValidationStatus",
    "CapabilityName",
)
