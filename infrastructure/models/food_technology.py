"""Model evidence and validation Adapter for the App-owned Food feature."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, cast

from app.features.configuration.food import (
    EVIDENCE_MAX_AGE,
    FoodPlanner,
    FoodPortError,
    FoodPortInvalid,
    FoodSystemRole,
    StoredFoodDefaults,
    StoredFoodHealth,
    StoredFoodPackage,
    StoredFoodProposal,
    StoredModelEvidence,
    is_model_evidence_fresh,
    project_food_health,
)
from elfie.brain.food_port import FoodPackage as RuntimeFoodPackage
from infrastructure.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from infrastructure.models.model_reference import (
    ModelReferenceError,
    parse_model_reference,
)
from infrastructure.models.providers.profiles import get_product
from infrastructure.persistence.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderConnectionStoreError,
    ProviderModelRecord,
)
from infrastructure.persistence.report_records import ValidationObservation
from infrastructure.persistence.report_repository import ReportRepository

FOOD_CATALOG_VERSION = 1
FOOD_EMERGENCY_ID = "food_emergency"
FOOD_COMMON_ID = "food_common"
SYSTEM_FOOD_IDS = frozenset({FOOD_EMERGENCY_ID, FOOD_COMMON_ID})


class RuntimeFoodTechnologyAdapter:
    """Implement the Food feature's model-evidence and policy Port."""

    def food_defaults(self) -> StoredFoodDefaults:
        return StoredFoodDefaults(
            catalog_version=FOOD_CATALOG_VERSION,
            default_food_id=FOOD_COMMON_ID,
            emergency_food_id=FOOD_EMERGENCY_ID,
            system_food_ids=SYSTEM_FOOD_IDS,
        )

    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]:
        try:
            evidence = query_model_evidence()
        except (
            OSError,
            ValueError,
            sqlite3.Error,
            ProviderConnectionStoreError,
        ) as error:
            raise FoodPortError("Unable to read model evidence") from error
        return tuple(evidence.values())

    def validate_package(self, package: StoredFoodPackage) -> None:
        try:
            validate_food_package_model_references(package)
        except (
            ModelReferenceError,
            OSError,
            ValueError,
            ProviderConnectionStoreError,
        ) as error:
            raise FoodPortInvalid(str(error)) from error

    def project_health(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
    ) -> StoredFoodHealth:
        try:
            return project_food_health(
                package,
                {item.reference: item for item in evidence},
            )
        except (TypeError, ValueError) as error:
            raise FoodPortError("Unable to project Food health") from error

    def propose_package(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
        *,
        connection_ids: tuple[str, ...],
        local_first: bool,
        allow_remote: bool,
    ) -> StoredFoodProposal:
        try:
            return FoodPlanner().propose_package(
                package,
                evidence,
                connection_ids=connection_ids,
                local_first=local_first,
                allow_remote=allow_remote,
            )
        except (TypeError, ValueError) as error:
            raise FoodPortError("Unable to generate Food preview") from error


def query_model_evidence(
    *,
    repository: Optional[ReportRepository] = None,
    connection_store: Optional[ProviderConnectionStore] = None,
    connections: Optional[Mapping[str, ProviderConnection]] = None,
    observations: Optional[Sequence[ValidationObservation]] = None,
    now: Optional[datetime] = None,
) -> dict[str, StoredModelEvidence]:
    """Project endpoint models and their latest immutable validation facts."""
    latest = observations
    if latest is None:
        latest = (repository or ReportRepository()).current(subject_kind="model")
    by_subject = {
        item.subject_id: item for item in latest if item.subject_kind == "model"
    }
    current = now or datetime.now(timezone.utc)
    result: dict[str, StoredModelEvidence] = {}
    inventory = (
        connections
        if connections is not None
        else (connection_store or ProviderConnectionStore()).load().connections
    )
    for connection in inventory.values():
        if not connection.enabled or connection.archived:
            continue
        profile = get_product(connection.catalog_id)
        is_local = bool(profile and profile.connection_method == "local")
        for model in connection.models:
            subject_id = f"{connection.connection_id}/{model.endpoint_model_id}"
            result[subject_id] = _project_model(
                subject_id,
                model,
                by_subject.get(subject_id),
                is_local=is_local,
                now=current,
            )
    return result


def record_model_evidence(
    evidence: Sequence[StoredModelEvidence],
    *,
    repository: Optional[ReportRepository] = None,
    scope: str,
    trigger: str,
) -> Optional[str]:
    """Append validation results through the report repository's only writer API."""
    if not evidence:
        return None
    report_repository = repository or ReportRepository()
    run_id = report_repository.start_run(scope=scope, trigger=trigger)
    for item in evidence:
        report_repository.append_observation(
            run_id=run_id,
            subject_kind="model",
            subject_id=item.reference,
            observed_at=item.observed_at or None,
            status="passed" if item.verified else "failed",
            latency_ms=item.latency_ms,
            details={
                "capabilities": sorted(item.capabilities),
                "cost_grade": item.cost_grade,
                "tool_test_passed": item.tool_test_passed,
            },
        )
    report_repository.finish_run(run_id, status="complete")
    return run_id


def validate_food_package_model_references(package: StoredFoodPackage) -> None:
    """Validate one Food against the current provider/model inventory."""
    connections = ProviderConnectionStore().load().connections
    for reference_value in package.model_references:
        try:
            reference = parse_model_reference(reference_value)
        except ModelReferenceError as error:
            raise ModelReferenceError(
                f"粮食 '{package.food_id}' 的模型无效: {error}"
            ) from error
        connection = connections.get(reference.connection_id)
        if connection is None or not connection.enabled or connection.archived:
            raise ModelReferenceError(f"粮食 '{package.food_id}' 引用了不可用连接")
        model = next(
            (
                item
                for item in connection.models
                if item.endpoint_model_id == reference.model_id
            ),
            None,
        )
        if model is None or model.hidden or model.retired or not model.available:
            raise ModelReferenceError(f"粮食 '{package.food_id}' 引用了不可用模型")


def stored_food_package(package: RuntimeFoodPackage) -> StoredFoodPackage:
    """Map the Elfie-owned read projection to the App Food boundary model."""
    return StoredFoodPackage(
        food_id=package.key,
        display_name=package.display_name,
        system_role=cast(
            Optional[FoodSystemRole],
            package.system_role
            if package.system_role in {"emergency", "common"}
            else None,
        ),
        enabled=package.enabled,
        archived=package.archived,
        primary_model=None if package.primary is None else package.primary.model,
        reasoning_model=None if package.reasoning is None else package.reasoning.model,
        vision_model=None if package.vision is None else package.vision.model,
        tool_model=None if package.tool is None else package.tool.model,
        fallback_model=None if package.fallback is None else package.fallback.model,
    )


def _project_model(
    subject_id: str,
    model: ProviderModelRecord,
    observation: Optional[ValidationObservation],
    *,
    is_local: bool,
    now: datetime,
) -> StoredModelEvidence:
    state = _validation_state(model, observation, now)
    details: Mapping[str, Any] = observation.details if observation else {}
    raw_capabilities = details.get("capabilities", ())
    observed_capabilities = (
        frozenset(str(item) for item in raw_capabilities)
        if isinstance(raw_capabilities, (list, tuple, set))
        else frozenset()
    )
    capabilities = observed_capabilities | known_capabilities(
        model.endpoint_model_id,
        model.display_name,
    )
    if model.supports_tools:
        capabilities |= {"tools"}
    if model.supports_vision:
        capabilities |= {"vision"}
    if model.supports_reasoning:
        capabilities |= {"reasoning"}
    evidence = StoredModelEvidence(
        reference=subject_id,
        display_name=canonical_display_name(subject_id, model.display_name),
        capabilities=capabilities or frozenset({"text"}),
        verified=state == "verified",
        cost_grade=_int_value(details, "cost_grade", 2),
        latency_ms=observation.latency_ms if observation else None,
        tool_test_passed=bool(details.get("tool_test_passed", False)),
        local=is_local,
        observed_at=observation.observed_at if observation else "",
        status=state,
    )
    return replace(evidence, fresh=is_model_evidence_fresh(evidence, now))


def _validation_state(
    model: ProviderModelRecord,
    observation: Optional[ValidationObservation],
    now: datetime,
) -> str:
    if model.hidden:
        return "hidden"
    if model.retired:
        return "retired"
    if not model.available:
        return "unavailable"
    if observation is None:
        return "never_verified"
    if observation.status != "passed":
        return "failed"
    try:
        observed = datetime.fromisoformat(
            observation.observed_at.replace("Z", "+00:00")
        )
    except ValueError:
        return "stale"
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return "verified" if now - observed <= EVIDENCE_MAX_AGE else "stale"


def _int_value(data: Mapping[str, Any], key: str, default: int) -> int:
    value = data.get(key)
    return (
        int(value)
        if isinstance(value, int) and not isinstance(value, bool)
        else default
    )


__all__ = (
    "RuntimeFoodTechnologyAdapter",
    "query_model_evidence",
    "record_model_evidence",
    "stored_food_package",
    "validate_food_package_model_references",
)
