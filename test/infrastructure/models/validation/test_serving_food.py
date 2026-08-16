from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.features.configuration.food import (
    StoredElfieFoodAssignment,
    StoredFoodPackage,
)
from infrastructure.models.report_records import ValidationObservation
from infrastructure.models.validation.serving_food import build_serving_food_index


def _package(
    food_id: str,
    primary: str,
    *,
    reasoning: str | None = None,
    vision: str | None = None,
    fallback: str | None = None,
    system_role: str | None = None,
    required_roles: frozenset[str] = frozenset(),
) -> StoredFoodPackage:
    return StoredFoodPackage(
        food_id=food_id,
        display_name=food_id,
        system_role=system_role,
        primary_model=primary,
        reasoning_model=reasoning,
        vision_model=vision,
        fallback_model=fallback,
        required_roles=required_roles,
    )


def _observation(
    reference: str,
    observed_at: str,
    *,
    food_id: str,
    semantic_role: str,
) -> ValidationObservation:
    return ValidationObservation(
        observation_id=1,
        run_id="run_1",
        subject_kind="model",
        subject_id=reference,
        observed_at=observed_at,
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details={
            "food_id": food_id,
            "semantic_role": semantic_role,
            "workload_kind": "production",
        },
    )


def test_only_selected_and_recently_used_foods_enter_core_scope() -> None:
    now = datetime.now(timezone.utc)
    packages = (
        _package(
            "food_selected",
            "cloud/main",
            reasoning="cloud/reason",
            vision="cloud/vision",
            fallback="cloud/fallback",
        ),
        _package("food_unused", "cloud/unused"),
        _package("food_emergency", "cloud/emergency", system_role="emergency"),
    )
    index = build_serving_food_index(
        packages,
        (StoredElfieFoodAssignment("elfie-1", 7, "food_selected"),),
        default_food_id="food_selected",
        emergency_food_id="food_emergency",
        observations=(
            _observation(
                "cloud/vision",
                (now - timedelta(days=31)).isoformat(),
                food_id="food_selected",
                semantic_role="vision",
            ),
        ),
        now=now,
    )

    assert {item.food_id for item in index.foods} == {
        "food_emergency",
        "food_selected",
    }
    assert "cloud/main" in index.core_references
    assert "cloud/fallback" in index.core_references
    assert "cloud/vision" not in index.core_references
    assert "cloud/unused" not in index.core_references


def test_recent_optional_role_usage_activates_exact_endpoint() -> None:
    now = datetime.now(timezone.utc)
    index = build_serving_food_index(
        (_package("food_selected", "cloud/main", vision="cloud/vision"),),
        (StoredElfieFoodAssignment("elfie-1", 7, "food_selected"),),
        default_food_id="food_selected",
        emergency_food_id="food_emergency",
        observations=(
            _observation(
                "cloud/vision",
                (now - timedelta(days=2)).isoformat(),
                food_id="food_selected",
                semantic_role="vision",
            ),
        ),
        now=now,
    )

    vision = next(
        item for item in index.core_endpoints if item.reference == "cloud/vision"
    )
    assert vision.food_ids == ("food_selected",)
    assert vision.roles == ("vision",)


def test_required_optional_role_is_core_without_recent_usage() -> None:
    package = StoredFoodPackage(
        food_id="food_selected",
        display_name="food_selected",
        primary_model="cloud/main",
        vision_model="cloud/vision",
        required_roles=frozenset({"vision"}),
    )

    index = build_serving_food_index(
        (package,),
        (StoredElfieFoodAssignment("elfie-1", 7, "food_selected"),),
        default_food_id="food_selected",
        emergency_food_id="food_emergency",
    )

    vision = next(
        item for item in index.core_endpoints if item.reference == "cloud/vision"
    )
    assert vision.roles == ("vision",)
