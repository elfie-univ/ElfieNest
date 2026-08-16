"""Pure projection of production-serving Foods and their core model routes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping

from app.features.configuration.food import (
    StoredElfieFoodAssignment,
    StoredFoodPackage,
)
from infrastructure.models.report_records import ValidationObservation

DIRECT_USE_LEASE = timedelta(hours=24)
OPTIONAL_ROLE_LEASE = timedelta(days=30)
_OPTIONAL_ROLES = ("reasoning", "vision", "tool")


@dataclass(frozen=True)
class ServingFoodRoute:
    food_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CoreEndpointRoute:
    reference: str
    food_ids: tuple[str, ...]
    roles: tuple[str, ...]


@dataclass(frozen=True)
class ServingFoodIndex:
    generation: str
    foods: tuple[ServingFoodRoute, ...]
    core_endpoints: tuple[CoreEndpointRoute, ...]

    @property
    def core_references(self) -> tuple[str, ...]:
        return tuple(item.reference for item in self.core_endpoints)


def build_serving_food_index(
    packages: Iterable[StoredFoodPackage],
    assignments: Iterable[StoredElfieFoodAssignment],
    *,
    default_food_id: str,
    emergency_food_id: str,
    observations: Iterable[ValidationObservation] = (),
    resolvable_references: Iterable[str] | None = None,
    now: datetime | None = None,
) -> ServingFoodIndex:
    """Derive active Food routes without copying Runtime selection SQL.

    The projection deliberately does not inspect model health.  A selected Food
    remains in scope while its current Endpoint is unhealthy so recovery checks
    can restore the same production route.
    """
    current = _utc(now or datetime.now(timezone.utc))
    package_map = {item.food_id: item for item in packages}
    resolvable = None if resolvable_references is None else set(resolvable_references)
    assignment_rows = tuple(assignments)
    production_observations = tuple(
        item
        for item in observations
        if item.details.get("workload_kind") == "production"
    )
    direct_food_reasons: dict[str, set[str]] = {}
    optional_role_foods: dict[str, set[str]] = {role: set() for role in _OPTIONAL_ROLES}
    for observation in production_observations:
        food_id = _text(observation.details.get("food_id"))
        if not food_id:
            continue
        observed_at = _parse(observation.observed_at)
        if observed_at is None:
            continue
        age = max(current - observed_at, timedelta(0))
        if age <= DIRECT_USE_LEASE:
            direct_food_reasons.setdefault(food_id, set()).add("direct_use_24h")
        if age <= OPTIONAL_ROLE_LEASE:
            role = _text(observation.details.get("semantic_role"))
            if role in optional_role_foods:
                optional_role_foods[role].add(food_id)

    serving_reasons: dict[str, set[str]] = {
        food_id: set(reasons) for food_id, reasons in direct_food_reasons.items()
    }
    for assignment in assignment_rows:
        selected = assignment.main_food_id or default_food_id
        package = package_map.get(selected)
        if package is not None and _visible_to_assignment(package, assignment):
            serving_reasons.setdefault(selected, set()).add(
                "elfie_selection" if assignment.main_food_id else "default_food"
            )
    if assignment_rows:
        emergency = package_map.get(emergency_food_id)
        if emergency is not None:
            serving_reasons.setdefault(emergency_food_id, set()).add(
                "global_emergency_fallback"
            )

    serving = {
        food_id: reasons
        for food_id, reasons in serving_reasons.items()
        if _is_serving_package(package_map.get(food_id), resolvable)
    }
    foods = tuple(
        ServingFoodRoute(food_id, tuple(sorted(reasons)))
        for food_id, reasons in sorted(serving.items())
    )

    endpoint_roles: dict[str, dict[str, set[str]]] = {}
    for food_id in serving:
        package = package_map[food_id]
        for role, reference in _package_roles(package).items():
            if (
                role in _OPTIONAL_ROLES
                and role not in getattr(package, "required_roles", frozenset())
                and food_id not in optional_role_foods[role]
            ):
                continue
            endpoint_roles.setdefault(reference, {}).setdefault(food_id, set()).add(
                role
            )
        # Primary is required for a serving Food.  A configured fallback protects
        # the same route even before the first fallback attempt occurs.
        if package.fallback_model:
            endpoint_roles.setdefault(package.fallback_model, {}).setdefault(
                food_id, set()
            ).add("fallback")

    core_endpoints = tuple(
        CoreEndpointRoute(
            reference=reference,
            food_ids=tuple(sorted(food_ids)),
            roles=tuple(sorted(role for roles in food_ids.values() for role in roles)),
        )
        for reference, food_ids in sorted(endpoint_roles.items())
    )
    generation = _generation(foods, core_endpoints)
    return ServingFoodIndex(generation, foods, core_endpoints)


def _is_serving_package(
    package: StoredFoodPackage | None,
    resolvable_references: set[str] | None,
) -> bool:
    return bool(
        package is not None
        and package.enabled
        and not package.archived
        and package.primary_model
        and (
            resolvable_references is None
            or package.primary_model in resolvable_references
        )
    )


def _visible_to_assignment(
    package: StoredFoodPackage,
    assignment: StoredElfieFoodAssignment,
) -> bool:
    return package.visibility_mode == "global" or assignment.owner_user_id in set(
        package.visible_user_ids
    )


def _package_roles(package: StoredFoodPackage) -> Mapping[str, str]:
    values = {
        "primary": package.primary_model,
        "reasoning": package.reasoning_model,
        "vision": package.vision_model,
        "tool": package.tool_model,
    }
    return {
        role: reference
        for role, reference in values.items()
        if isinstance(reference, str) and reference.strip()
    }


def _generation(
    foods: tuple[ServingFoodRoute, ...],
    endpoints: tuple[CoreEndpointRoute, ...],
) -> str:
    payload = {
        "foods": [(item.food_id, item.reasons) for item in foods],
        "endpoints": [
            (item.reference, item.food_ids, item.roles) for item in endpoints
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _parse(value: str) -> datetime | None:
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = (
    "CoreEndpointRoute",
    "DIRECT_USE_LEASE",
    "OPTIONAL_ROLE_LEASE",
    "ServingFoodIndex",
    "ServingFoodRoute",
    "build_serving_food_index",
)
