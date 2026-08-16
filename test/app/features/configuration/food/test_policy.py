from datetime import datetime, timedelta, timezone

from app.features.configuration.food import (
    FoodPlanner,
    StoredElfieFoodAssignment,
    StoredFoodPackage,
    StoredModelEvidence,
    project_food_health,
    project_model_service_health,
)


def _evidence(
    reference: str,
    *,
    local: bool = False,
    age: int = 0,
    capabilities: tuple[str, ...] = ("text",),
) -> StoredModelEvidence:
    return StoredModelEvidence(
        reference=reference,
        display_name=reference,
        capabilities=frozenset(capabilities),
        verified=True,
        local=local,
        tool_test_passed="tools" in capabilities,
        observed_at=(datetime.now(timezone.utc) - timedelta(hours=age)).isoformat(),
    )


def test_planner_uses_only_fresh_scoped_models_and_local_first() -> None:
    proposal = FoodPlanner().propose_package(
        StoredFoodPackage(
            food_id="food_emergency",
            display_name="保底",
            system_role="emergency",
        ),
        (
            _evidence("cloud_0001/fast"),
            _evidence("ollama_0001/local", local=True),
            _evidence("ollama_0001/stale", local=True, age=48),
        ),
        connection_ids=("ollama_0001", "cloud_0001"),
        local_first=True,
    )

    assert proposal.package.primary_model == "ollama_0001/local"
    assert proposal.package.fallback_model == "cloud_0001/fast"
    assert "stale" not in proposal.package.model_references


def test_health_uses_primary_and_same_food_fallback_evidence() -> None:
    package = StoredFoodPackage(
        food_id="food_custom",
        display_name="Custom",
        enabled=True,
        primary_model="cloud/main",
        fallback_model="local/backup",
    )
    evidence = {
        "cloud/main": _evidence("cloud/main", age=48),
        "local/backup": _evidence("local/backup", local=True),
    }

    health = project_food_health(package, evidence)

    assert health.status == "degraded"
    assert health.locality == "mixed"


def test_model_service_health_ignores_inactive_models_and_requires_emergency_food() -> (
    None
):
    packages = (
        StoredFoodPackage(
            food_id="food_common",
            display_name="Common",
            system_role="common",
            primary_model="cloud/main",
        ),
        StoredFoodPackage(
            food_id="food_emergency",
            display_name="Emergency",
            system_role="emergency",
            primary_model="ollama/backup",
        ),
        StoredFoodPackage(
            food_id="food_inactive",
            display_name="Unused",
            primary_model="broken/model",
        ),
    )

    health = project_model_service_health(
        packages,
        (_evidence("cloud/main"), _evidence("ollama/backup", local=True)),
    )

    assert health.status == "healthy"
    assert health.common_status == "healthy"
    assert health.emergency_status == "healthy"
    assert health.required_food_ids == ("food_common", "food_emergency")


def test_required_role_needs_verified_capability_evidence() -> None:
    package = StoredFoodPackage(
        food_id="food_common",
        display_name="Common",
        primary_model="cloud/main",
        vision_model="cloud/vision",
        required_roles=frozenset({"vision"}),
    )
    evidence = (
        _evidence("cloud/main"),
        StoredModelEvidence(
            reference="cloud/vision",
            display_name="cloud/vision",
            capabilities=frozenset({"text", "vision"}),
            verified=True,
            capability_states={"vision": "unsupported"},
            observed_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    health = project_food_health(package, {item.reference: item for item in evidence})

    assert health.status == "unavailable"


def test_model_service_health_degrades_for_missing_emergency_but_unavailable_common_blocks() -> (
    None
):
    packages = (
        StoredFoodPackage(
            food_id="food_common",
            display_name="Common",
            system_role="common",
            primary_model="cloud/main",
        ),
    )

    degraded = project_model_service_health(packages, (_evidence("cloud/main"),))
    unavailable = project_model_service_health(packages, ())

    assert degraded.status == "degraded"
    assert degraded.emergency_status == "unavailable"
    assert unavailable.status == "unavailable"
    assert unavailable.common_status == "unavailable"


def test_model_service_health_includes_food_used_by_an_active_elfie() -> None:
    packages = (
        StoredFoodPackage(
            food_id="food_common",
            display_name="Common",
            system_role="common",
            primary_model="cloud/main",
        ),
        StoredFoodPackage(
            food_id="food_emergency",
            display_name="Emergency",
            system_role="emergency",
            primary_model="ollama/backup",
        ),
        StoredFoodPackage(
            food_id="food_elfie",
            display_name="Elfie route",
            primary_model="cloud/elfie",
        ),
    )

    health = project_model_service_health(
        packages,
        (_evidence("cloud/main"), _evidence("ollama/backup", local=True)),
        active_assignments=(StoredElfieFoodAssignment("elfie-1", 1, "food_elfie"),),
    )

    assert health.status == "unavailable"
    assert health.common_status == "unavailable"
    assert health.required_food_ids == (
        "food_common",
        "food_elfie",
        "food_emergency",
    )
