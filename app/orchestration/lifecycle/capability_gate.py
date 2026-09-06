"""Server-side capability requirements for the Runtime projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ModelOverallState,
    RuntimeProjectionV1,
    RuntimeTarget,
)

ModelRequirement = Literal["none", "common", "emergency", "all"]


class CapabilityDeniedError(RuntimeError):
    """A product operation is not allowed by the current Runtime projection."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class CapabilityRequirement:
    """Minimum backend and model projection required by one operation."""

    operation: str
    backend: RuntimeTarget = RuntimeTarget.CORE
    model: ModelRequirement = "none"


@dataclass(frozen=True)
class CapabilityPermit:
    """Generation- and revision-bound permission for one server operation."""

    operation: str
    instance_id: str
    generation: int
    snapshot_revision: int
    model_revision: int | None

    def valid_for(self, projection: RuntimeProjectionV1) -> bool:
        return (
            projection.instance_id == self.instance_id
            and projection.generation == self.generation
            and projection.revision == self.snapshot_revision
            and projection.model_revision == self.model_revision
        )


class CapabilityRequirementRegistry:
    """Immutable operation-to-requirement registry owned by Bootstrap."""

    def __init__(
        self,
        requirements: Mapping[str, CapabilityRequirement],
    ) -> None:
        if any(key != value.operation for key, value in requirements.items()):
            raise ValueError("capability registry keys must match operation names")
        self._requirements = dict(requirements)

    def requirement_for(self, operation: str) -> CapabilityRequirement:
        try:
            return self._requirements[operation]
        except KeyError as error:
            raise CapabilityDeniedError(
                "UNKNOWN_CAPABILITY",
                f"No Runtime requirement is registered for {operation!r}",
            ) from error

    def issue(
        self,
        operation: str,
        projection: RuntimeProjectionV1,
    ) -> CapabilityPermit:
        requirement = self.requirement_for(operation)
        _require_backend(requirement, projection)
        _require_model(requirement, projection)
        return CapabilityPermit(
            operation=operation,
            instance_id=projection.instance_id,
            generation=projection.generation,
            snapshot_revision=projection.revision,
            model_revision=projection.model_revision,
        )


DEFAULT_CAPABILITY_REQUIREMENTS = CapabilityRequirementRegistry(
    {
        "setup": CapabilityRequirement("setup"),
        "sign_in": CapabilityRequirement("sign_in"),
        "configuration": CapabilityRequirement("configuration"),
        "status": CapabilityRequirement("status"),
        "repair": CapabilityRequirement("repair"),
        "world": CapabilityRequirement("world", RuntimeTarget.WORLD),
        "chat": CapabilityRequirement("chat", model="common"),
        "adoption": CapabilityRequirement(
            "adoption", RuntimeTarget.WORLD, model="common"
        ),
    }
)


def _require_backend(
    requirement: CapabilityRequirement,
    projection: RuntimeProjectionV1,
) -> None:
    required_tier = (
        BackendTier.WORLD_READY
        if requirement.backend.rank >= RuntimeTarget.WORLD.rank
        else BackendTier.CORE_READY
    )
    if required_tier is BackendTier.CORE_READY:
        allowed = projection.tier in {BackendTier.CORE_READY, BackendTier.WORLD_READY}
    else:
        allowed = projection.tier is BackendTier.WORLD_READY
    if not allowed:
        raise CapabilityDeniedError(
            "BACKEND_NOT_READY",
            f"{requirement.operation} requires {required_tier.value}; current tier is {projection.tier.value}",
        )


def _require_model(
    requirement: CapabilityRequirement,
    projection: RuntimeProjectionV1,
) -> None:
    if requirement.model == "none":
        return
    if requirement.model == "all":
        if projection.model_state is not ModelOverallState.READY:
            raise CapabilityDeniedError(
                "MODEL_SERVICE_NOT_READY",
                f"{requirement.operation} requires READY model service; current state is {projection.model_state.value}",
            )
        return
    state = (
        projection.model_common_state
        if requirement.model == "common"
        else projection.model_emergency_state
    )
    if state not in {ModelOverallState.READY, ModelOverallState.DEGRADED}:
        raise CapabilityDeniedError(
            "MODEL_ROUTE_UNAVAILABLE",
            f"{requirement.operation} has no executable {requirement.model} model route",
        )


__all__ = (
    "CapabilityDeniedError",
    "CapabilityPermit",
    "CapabilityRequirement",
    "CapabilityRequirementRegistry",
    "DEFAULT_CAPABILITY_REQUIREMENTS",
    "ModelRequirement",
)
