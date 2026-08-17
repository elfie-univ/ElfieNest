from dataclasses import replace

import pytest

from app.orchestration.lifecycle.capability_gate import (
    DEFAULT_CAPABILITY_REQUIREMENTS,
    CapabilityDeniedError,
)
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ModelOverallState,
    RuntimePhase,
    RuntimeProjectionV1,
    RuntimeTarget,
)


def _projection(
    *,
    tier: BackendTier = BackendTier.CORE_READY,
    model: ModelOverallState = ModelOverallState.READY,
    common: ModelOverallState = ModelOverallState.READY,
    emergency: ModelOverallState = ModelOverallState.READY,
) -> RuntimeProjectionV1:
    return RuntimeProjectionV1(
        schema_version=1,
        instance_id="instance",
        generation=4,
        revision=9,
        tier=tier,
        phase=RuntimePhase.WORLD_READY
        if tier is BackendTier.WORLD_READY
        else RuntimePhase.CORE_READY,
        subphase="",
        desired_target=RuntimeTarget.NORMAL,
        reached_target=RuntimeTarget.WORLD
        if tier is BackendTier.WORLD_READY
        else RuntimeTarget.CORE,
        model_state=model,
        model_common_state=common,
        model_emergency_state=emergency,
        model_revision=3,
    )


def test_core_setup_permit_is_bound_to_the_current_snapshot_revision() -> None:
    projection = _projection()
    permit = DEFAULT_CAPABILITY_REQUIREMENTS.issue("setup", projection)

    assert permit.valid_for(projection)
    assert not permit.valid_for(replace(projection, revision=10))


@pytest.mark.parametrize(
    "operation", ["setup", "sign_in", "configuration", "status", "repair"]
)
def test_core_operation_matrix_is_available_at_core_ready(operation: str) -> None:
    permit = DEFAULT_CAPABILITY_REQUIREMENTS.issue(operation, _projection())

    assert permit.operation == operation


def test_world_operation_matrix_requires_world_ready() -> None:
    with pytest.raises(CapabilityDeniedError) as error:
        DEFAULT_CAPABILITY_REQUIREMENTS.issue("world", _projection())

    assert error.value.code == "BACKEND_NOT_READY"
    assert (
        DEFAULT_CAPABILITY_REQUIREMENTS.issue(
            "world", _projection(tier=BackendTier.WORLD_READY)
        ).operation
        == "world"
    )


def test_chat_accepts_an_executable_degraded_common_route() -> None:
    projection = _projection(
        model=ModelOverallState.DEGRADED,
        common=ModelOverallState.DEGRADED,
    )

    permit = DEFAULT_CAPABILITY_REQUIREMENTS.issue("chat", projection)

    assert permit.operation == "chat"


def test_chat_is_rejected_without_a_common_route() -> None:
    with pytest.raises(CapabilityDeniedError) as error:
        DEFAULT_CAPABILITY_REQUIREMENTS.issue(
            "chat",
            _projection(
                model=ModelOverallState.UNAVAILABLE,
                common=ModelOverallState.UNAVAILABLE,
            ),
        )

    assert error.value.code == "MODEL_ROUTE_UNAVAILABLE"


def test_adoption_requires_world_and_fully_ready_models() -> None:
    with pytest.raises(CapabilityDeniedError) as error:
        DEFAULT_CAPABILITY_REQUIREMENTS.issue(
            "adoption",
            _projection(tier=BackendTier.WORLD_READY, model=ModelOverallState.DEGRADED),
        )

    assert error.value.code == "MODEL_SERVICE_NOT_READY"


def test_adoption_matrix_rejects_missing_emergency_reserve() -> None:
    with pytest.raises(CapabilityDeniedError) as error:
        DEFAULT_CAPABILITY_REQUIREMENTS.issue(
            "adoption",
            _projection(
                tier=BackendTier.WORLD_READY,
                model=ModelOverallState.DEGRADED,
                common=ModelOverallState.READY,
                emergency=ModelOverallState.UNAVAILABLE,
            ),
        )

    assert error.value.code == "MODEL_SERVICE_NOT_READY"
