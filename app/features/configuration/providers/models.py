"""Commands, queries and results owned by Provider administration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Literal, Mapping

from .port_models import (
    ApiMode,
    AuthType,
    CapabilityName,
    ConnectionMethod,
    DiscoveryStrategy,
    LatencyClass,
    LocalProviderState,
    ModelSource,
    StoredCapabilityProbeResult,
    StoredEndpointCapability,
    ValidationMode,
    ValidationStatus,
)

ConnectionUpdateField = Literal[
    "alias", "api_base", "api_key", "api_mode", "auth_type", "models"
]
ModelUpdateField = Literal[
    "display_name",
    "canonical_model_id",
    "context_window_tokens",
    "max_output_tokens",
    "supports_tools",
    "supports_vision",
    "supports_reasoning",
    "supports_structured_output",
    "request_profile_id",
    "request_profile_version",
    "hidden",
    "retired",
]
LifecycleAction = Literal["enable", "disable", "archive", "restore"]
LocalProviderTaskKey = Literal["install", "model_pull"]
LocalProviderTaskState = Literal["running", "completed", "failed"]


@dataclass(frozen=True)
class ProviderModelInput:
    model_id: str
    display_name: str = ""
    canonical_model_id: str | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    supports_reasoning: bool | None = None
    supports_structured_output: bool | None = None
    request_profile_id: str | None = None
    request_profile_version: int | None = None


@dataclass(frozen=True)
class ProviderModelReplacement(ProviderModelInput):
    original_model_id: str = ""
    hidden: bool = False
    # ``None`` means a typed caller supplied a complete replacement record;
    # the HTTP adapter passes the actual field set so omitted optional fields
    # cannot erase endpoint-specific metadata.
    fields: FrozenSet[str] | None = None


@dataclass(frozen=True)
class ListProviderProductsQuery:
    pass


@dataclass(frozen=True)
class ListProviderConnectionsQuery:
    pass


@dataclass(frozen=True)
class InspectLocalProviderQuery:
    pass


@dataclass(frozen=True)
class EnsureDefaultLocalProviderConnectionCommand:
    pass


@dataclass(frozen=True)
class DefaultLocalProviderConnectionResult:
    catalog_id: str
    ensured: bool


@dataclass(frozen=True)
class InstallLocalProviderCommand:
    confirmed: bool


@dataclass(frozen=True)
class StartLocalProviderCommand:
    pass


@dataclass(frozen=True)
class PullLocalProviderModelsCommand:
    model_ids: tuple[str, ...]
    confirmed: bool


@dataclass(frozen=True)
class CreateProviderConnectionCommand:
    catalog_id: str
    alias: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    api_mode: ApiMode | None = None
    auth_type: AuthType | None = None
    models: tuple[ProviderModelInput, ...] = ()
    verify: bool = False
    refresh_models: bool = True


@dataclass(frozen=True)
class StartProviderOAuthLoginCommand:
    catalog_id: str


@dataclass(frozen=True)
class CompleteProviderOAuthLoginCommand:
    catalog_id: str
    login_id: str
    alias: str | None = None


@dataclass(frozen=True)
class UpdateProviderConnectionCommand:
    connection_id: str
    fields: FrozenSet[ConnectionUpdateField]
    alias: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    api_mode: ApiMode | None = None
    auth_type: AuthType | None = None
    models: tuple[ProviderModelInput, ...] | None = None
    verify: bool = False
    refresh_models: bool = False


@dataclass(frozen=True)
class DeleteProviderConnectionCommand:
    connection_id: str


@dataclass(frozen=True)
class RemoveLocalProviderConnectionCommand:
    connection_id: str


@dataclass(frozen=True)
class ChangeProviderConnectionLifecycleCommand:
    connection_id: str
    action: LifecycleAction


@dataclass(frozen=True)
class VerifyProviderConnectionCommand:
    connection_id: str
    force_full: bool = False


@dataclass(frozen=True)
class RefreshProviderModelsCommand:
    connection_id: str


@dataclass(frozen=True)
class AddProviderModelCommand:
    connection_id: str
    model: ProviderModelInput


@dataclass(frozen=True)
class ReplaceProviderModelsCommand:
    connection_id: str
    models: tuple[ProviderModelReplacement, ...]


@dataclass(frozen=True)
class UpdateProviderModelCommand:
    connection_id: str
    model_id: str
    fields: FrozenSet[ModelUpdateField]
    display_name: str | None = None
    canonical_model_id: str | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    supports_reasoning: bool | None = None
    supports_structured_output: bool | None = None
    request_profile_id: str | None = None
    request_profile_version: int | None = None
    hidden: bool | None = None
    retired: bool | None = None


@dataclass(frozen=True)
class DeleteProviderModelCommand:
    connection_id: str
    model_id: str


@dataclass(frozen=True)
class ProbeProviderModelCapabilitiesCommand:
    connection_id: str
    model_id: str
    capabilities: tuple[CapabilityName, ...] = ()


@dataclass(frozen=True)
class ListObsoleteProviderModelsQuery:
    connection_id: str


@dataclass(frozen=True)
class CleanupObsoleteProviderModelsCommand:
    connection_id: str
    # Empty means the legacy explicit Owner action: clean every currently
    # eligible source-managed model.  The model-management endpoint always
    # supplies a non-empty selection so the normal UI remains intentional.
    model_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GetProviderModelMatrixQuery:
    as_of: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class BenchmarkCombination:
    connection_id: str
    model_id: str


@dataclass(frozen=True)
class BenchmarkProviderModelsCommand:
    combinations: tuple[BenchmarkCombination, ...]


@dataclass(frozen=True)
class ValidateAllProviderModelsCommand:
    pass


@dataclass(frozen=True)
class ProviderBrandResult:
    brand_id: str
    name: str
    logo_asset: str


@dataclass(frozen=True)
class ProviderProductResult:
    catalog_id: str
    name: str
    brand: ProviderBrandResult
    connection_method: ConnectionMethod
    oauth_available: bool
    usage_scope: str
    discovery_strategy: DiscoveryStrategy
    api_mode: ApiMode
    api_base: str
    auth_type: AuthType


@dataclass(frozen=True)
class ProviderVerificationResult:
    status: ValidationStatus
    checked_at: str | None
    latency_ms: float | None
    error: str | None
    validation_mode: ValidationMode
    cache_hit: bool
    needs_full_validation: bool
    needs_heartbeat: bool
    full_run_id: str | None
    full_checked_at: str | None
    heartbeat_checked_at: str | None
    heartbeat_status: Literal["passed", "failed"] | None
    representative_model_id: str | None
    reason: str | None
    availability_status: str = "unknown"
    reason_code: str | None = None
    evidence_source: str | None = None
    expires_at: str | None = None
    is_core: bool = False


@dataclass(frozen=True)
class ProviderModelResult:
    model_id: str
    display_name: str
    canonical_model_id: str | None
    source: ModelSource
    context_window_tokens: int | None
    max_output_tokens: int | None
    supports_tools: bool | None
    supports_vision: bool | None
    supports_reasoning: bool | None
    hidden: bool
    retired: bool
    available: bool
    verification: ProviderVerificationResult
    discovery_state: str = "present"
    consecutive_missing: int = 0
    last_seen_at: str | None = None
    request_profile_id: str | None = None
    request_profile_version: int | None = None
    supports_structured_output: bool | None = None
    capability_evidence: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderModelRefreshResult:
    status: str
    checked_at: str
    message: str | None
    models: tuple[ProviderModelResult, ...]


@dataclass(frozen=True)
class ProviderCapabilityProbeResult:
    reference: str
    results: tuple[StoredCapabilityProbeResult, ...]


@dataclass(frozen=True)
class ProviderObsoleteModelResult:
    model: ProviderModelResult
    eligible: bool
    reason: str
    last_production_at: str | None = None


@dataclass(frozen=True)
class ProviderConnectionResult:
    connection_id: str
    catalog_id: str
    alias: str
    api_base: str
    api_mode: ApiMode
    auth_type: AuthType
    has_api_key: bool
    enabled: bool
    archived: bool
    usage_scope: str
    verification: ProviderVerificationResult
    models: tuple[ProviderModelResult, ...]
    model_refresh: ProviderModelRefreshResult | None = None
    has_credential: bool = False


@dataclass(frozen=True)
class ProviderOAuthLoginStartResult:
    catalog_id: str
    login_id: str
    authorization_url: str
    user_code: str
    poll_interval_seconds: int
    expires_at: str


@dataclass(frozen=True)
class ProviderOAuthLoginStatusResult:
    catalog_id: str
    login_id: str
    state: Literal["pending", "completed"]
    account_id: str | None
    expires_at: str | None
    connection: ProviderConnectionResult | None


@dataclass(frozen=True)
class LocalProviderModelResult:
    model_id: str
    display_name: str
    installed: bool
    recommended: bool
    availability_status: Literal["available", "degraded", "unavailable", "unknown"] = (
        "unknown"
    )
    available: bool = False


@dataclass(frozen=True)
class LocalProviderTaskResult:
    key: LocalProviderTaskKey
    state: LocalProviderTaskState
    progress: int
    error: str | None


@dataclass(frozen=True)
class LocalProviderStatusResult:
    state: LocalProviderState
    endpoint: str | None
    version: str | None
    memory_gb: int
    recommended_model: str | None
    installed_model_count: int
    models: tuple[LocalProviderModelResult, ...]
    task: LocalProviderTaskResult | None


@dataclass(frozen=True)
class ProviderConnectionDeletedResult:
    connection_id: str


@dataclass(frozen=True)
class ProviderModelDeletedResult:
    connection_id: str
    model_id: str


@dataclass(frozen=True)
class ProviderModelsCleanupResult:
    connection_id: str
    model_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProviderConnectionVerificationResult:
    connection_id: str
    verification: ProviderVerificationResult


@dataclass(frozen=True)
class ProviderMatrixCellResult:
    connection_id: str
    model_id: str | None
    available: bool
    verification_status: ValidationStatus
    benchmark_status: Literal["passed", "failed"] | None
    latency_ms: float | None
    latency_class: LatencyClass | None
    price_estimate: float | None
    locality: Literal["local", "remote"] = "remote"
    validated_at: str | None = None
    time_to_first_token_ms: float | None = None
    total_latency_ms: float | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    validation_source: str | None = None
    capability_facts: tuple[StoredEndpointCapability, ...] = ()


@dataclass(frozen=True)
class ProviderMatrixModelResult:
    model_key: str
    display_name: str
    capabilities: tuple[str, ...]
    connections: tuple[ProviderMatrixCellResult, ...]


@dataclass(frozen=True)
class ProviderMatrixConnectionResult:
    connection_id: str
    name: str
    verification: ProviderVerificationResult


@dataclass(frozen=True)
class ProviderMatrixSnapshotResult:
    mode: str
    run_id: str | None
    as_of: str | None
    status: str | None
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class ProviderModelMatrixResult:
    snapshot: ProviderMatrixSnapshotResult
    connections: tuple[ProviderMatrixConnectionResult, ...]
    models: tuple[ProviderMatrixModelResult, ...]


@dataclass(frozen=True)
class ProviderBenchmarkResult:
    connection_id: str
    model_id: str
    status: Literal["passed", "failed"]
    checked_at: str
    latency_ms: float | None
    latency_class: LatencyClass | None
    error: str | None


@dataclass(frozen=True)
class ProviderBenchmarkRunResult:
    run_id: str
    status: str
    results: tuple[ProviderBenchmarkResult, ...]


@dataclass(frozen=True)
class ProviderValidationItemResult:
    subject: str
    status: str
    checked_at: str | None


@dataclass(frozen=True)
class ProviderValidationRunResult:
    run_id: str
    status: str
    results: tuple[ProviderValidationItemResult, ...]


__all__ = tuple(
    name
    for name in globals()
    if name.endswith(("Command", "Input", "Query", "Replacement", "Result"))
) + (
    "BenchmarkCombination",
    "ConnectionUpdateField",
    "LifecycleAction",
    "LocalProviderTaskKey",
    "LocalProviderTaskState",
    "ModelUpdateField",
)
