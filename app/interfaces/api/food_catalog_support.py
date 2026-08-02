"""Catalog parsing, lifecycle, and response projection for Owner food routes."""

from __future__ import annotations

import secrets
from dataclasses import replace
from typing import Any

from fastapi import HTTPException

from ai_runtime.food.evidence import query_model_evidence
from ai_runtime.food.health import project_food_health
from ai_runtime.food.models import FoodPackage
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.models.model_reference import ModelReferenceError


def stores() -> tuple[FoodCatalogStore, dict[str, Any]]:
    return FoodCatalogStore(), query_model_evidence()


def set_lifecycle(
    food_id: str,
    *,
    enabled: bool,
    archived: bool | None = None,
) -> dict[str, Any]:
    store, evidence = stores()
    current = store.load()
    package = require_package(current, food_id)
    if package.archived and enabled:
        raise HTTPException(status_code=409, detail="归档粮食必须先恢复")
    updated_package = replace(
        package,
        enabled=enabled,
        archived=package.archived if archived is None else archived,
    )
    updated = replace(
        current,
        packages={**current.packages, food_id: updated_package},
    )
    store.save(updated)
    return package_view(updated_package, evidence)


def parse_package(
    food_id: str,
    body: dict[str, Any],
    *,
    default_enabled: bool,
    system_role: str | None = None,
    archived: bool = False,
) -> FoodPackage:
    payload = {
        "display_name": str(body.get("display_name") or food_id).strip(),
        "system_role": system_role,
        "enabled": bool(body.get("enabled", default_enabled)),
        "archived": archived,
        "roles": body.get("roles", {}),
    }
    try:
        return FoodPackage.from_dict(food_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def save_checked(
    store: FoodCatalogStore,
    catalog: FoodCatalog,
    evidence: dict[str, Any],
) -> None:
    for package in catalog.packages.values():
        for reference in package.model_references:
            item = evidence.get(reference)
            if item is None or not item.is_fresh():
                raise HTTPException(
                    status_code=422,
                    detail=f"模型 {reference} 最近没有验证通过",
                )
    try:
        store.save(catalog)
    except (ModelReferenceError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def catalog_view(
    catalog: FoodCatalog,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": catalog.version,
        "global_default_food_id": catalog.global_default_food_id,
        "global_emergency_food_id": catalog.global_emergency_food_id,
        "packages": [
            package_view(package, evidence) for package in catalog.ordered_packages()
        ],
        "eligible_models": [
            {
                "reference": item.model,
                "display_name": item.display_name or item.model,
                "local": item.local,
                "capabilities": sorted(item.capabilities),
            }
            for item in evidence.values()
            if item.is_fresh()
        ],
    }


def package_view(
    package: FoodPackage,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    health = project_food_health(package, evidence)
    return {
        **package.to_dict(),
        "health": health.status,
        "locality": health.locality,
        "latest_evidence_at": health.latest_evidence_at,
    }


def require_package(catalog: FoodCatalog, food_id: str) -> FoodPackage:
    package = catalog.packages.get(food_id)
    if package is None:
        raise HTTPException(status_code=404, detail="未知粮食")
    return package


def new_food_key(catalog: FoodCatalog) -> str:
    while True:
        candidate = f"food_{secrets.token_hex(4)}"
        if candidate not in catalog.packages:
            return candidate


__all__ = (
    "catalog_view",
    "new_food_key",
    "package_view",
    "parse_package",
    "require_package",
    "save_checked",
    "set_lifecycle",
    "stores",
)
