"""Model evidence and validation Adapter for the App-owned Food feature."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Literal, Mapping, Optional, Protocol, Sequence, cast

from pydantic import JsonValue

from app.features.configuration.food import (
    EVIDENCE_MAX_AGE,
    FoodPlanner,
    FoodPortError,
    FoodPortInvalid,
    StoredFoodDefaults,
    StoredFoodHealth,
    StoredFoodPackage,
    StoredFoodProposal,
    StoredModelEvidence,
    is_model_evidence_fresh,
    project_food_health,
)
from app.features.configuration.food.port_models import CapabilityState
from elfie.brain.reasoning.food_port import FoodPackage as ModelExecutionFoodPackage
from infrastructure.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from infrastructure.models.model_reference import (
    ModelReferenceError,
    parse_model_reference,
)
from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.report_records import ValidationObservation

FOOD_CATALOG_VERSION = 1
FOOD_EMERGENCY_ID = "food_emergency"
FOOD_COMMON_ID = "food_common"
SYSTEM_FOOD_IDS = frozenset({FOOD_EMERGENCY_ID, FOOD_COMMON_ID})


class ModelFoodTechnologyAdapter:
    """Implement the Food feature's model-evidence and policy Port."""

    def __init__(self, evidence_port: FoodEvidencePort) -> None:
        self._evidence_port = evidence_port

    def food_defaults(self) -> StoredFoodDefaults:
        return StoredFoodDefaults(
            catalog_version=FOOD_CATALOG_VERSION,
            default_food_id=FOOD_COMMON_ID,
            emergency_food_id=FOOD_EMERGENCY_ID,
            system_food_ids=SYSTEM_FOOD_IDS,
        )

    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]:
        try:
            evidence = self._evidence_port.list_model_evidence()
        except (OSError, ValueError) as error:
            raise FoodPortError("Unable to read model evidence") from error
        return tuple(evidence)

    def validate_package(self, package: StoredFoodPackage) -> None:
        try:
            self._evidence_port.validate_package(package)
        except (ModelReferenceError, OSError, ValueError) as error:
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


class FoodEvidencePort(Protocol):
    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]: ...

    def record_model_evidence(
        self,
        evidence: list[StoredModelEvidence] | tuple[StoredModelEvidence, ...],
        *,
        scope: str,
        trigger: str,
    ) -> Optional[str]: ...

    def validate_package(self, package: StoredFoodPackage) -> None: ...


def validate_food_package_model_references(
    package: StoredFoodPackage,
    connections: Mapping[str, ProviderConnection],
) -> None:
    """Validate one Food against an injected Provider inventory."""
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
        if (
            model is None
            or model.hidden
            or model.retired
            or model.discovery_state != "present"
        ):
            raise ModelReferenceError(f"粮食 '{package.food_id}' 引用了不可用模型")


def stored_food_package(package: ModelExecutionFoodPackage) -> StoredFoodPackage:
    """Map the Elfie-owned read projection to the App Food boundary model."""
    return StoredFoodPackage(
        food_id=package.key,
        display_name=package.display_name,
        system_role=cast(
            Optional[Literal["emergency", "common"]],
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
    capability_observations: Sequence[ValidationObservation] = (),
) -> StoredModelEvidence:
    state = _validation_state(model, observation, now)
    details: Mapping[str, JsonValue] = observation.details if observation else {}
    raw_capabilities = details.get("capabilities", ())
    observed_capabilities = (
        frozenset(str(item) for item in raw_capabilities)
        if isinstance(raw_capabilities, (list, tuple, set))
        else frozenset()
    )
    capabilities = set(
        observed_capabilities
        | known_capabilities(
            model.endpoint_model_id,
            model.display_name,
        )
    )
    if model.supports_tools:
        capabilities |= {"tools"}
    if model.supports_vision:
        capabilities |= {"vision"}
    if model.supports_reasoning:
        capabilities |= {"reasoning"}
    capability_states: dict[str, CapabilityState] = {}
    seen_capabilities: set[str] = set()
    for capability_observation in capability_observations:
        capability = capability_observation.details.get("capability")
        capability_state = capability_observation.details.get("capability_state")
        if (
            isinstance(capability, str)
            and capability in {"tools", "vision", "reasoning", "structured_output"}
            and isinstance(capability_state, str)
            and capability_state in {"supported", "unsupported", "unknown"}
        ):
            # ``query_model_evidence`` supplies capability observations newest
            # first.  Keep the first valid observation for each channel so an
            # older result cannot overwrite a newer failure or unknown state.
            if capability in seen_capabilities:
                continue
            seen_capabilities.add(capability)
            capability_states[capability] = cast(CapabilityState, capability_state)
            if capability_state == "supported":
                capabilities.add(capability)
            elif capability_state == "unsupported":
                capabilities.discard(capability)
    evidence = StoredModelEvidence(
        reference=subject_id,
        display_name=canonical_display_name(subject_id, model.display_name),
        capabilities=frozenset(capabilities or {"text"}),
        verified=state == "verified",
        cost_grade=_int_value(details, "cost_grade", 2),
        latency_ms=observation.latency_ms if observation else None,
        tool_test_passed=bool(details.get("tool_test_passed", False))
        or capability_states.get("tools") == "supported",
        local=is_local,
        observed_at=observation.observed_at if observation else "",
        status=state,
        capability_states=capability_states,
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
    # ``available`` is read-only compatibility for pre-v2 documents.  New
    # writes omit it; current state is otherwise controlled by discovery and
    # append-only validation evidence.
    if not model.available or model.discovery_state != "present":
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


def _int_value(data: Mapping[str, JsonValue], key: str, default: int) -> int:
    value = data.get(key)
    return (
        int(value)
        if isinstance(value, int) and not isinstance(value, bool)
        else default
    )


__all__ = (
    "FoodEvidencePort",
    "ModelFoodTechnologyAdapter",
    "stored_food_package",
    "validate_food_package_model_references",
)
