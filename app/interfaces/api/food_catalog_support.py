"""Catalog parsing, lifecycle, and response projection for Owner food routes."""

from __future__ import annotations

import secrets
from dataclasses import replace
from typing import Any

from fastapi import HTTPException, Request

from ai_runtime.food.evidence import query_model_evidence
from ai_runtime.food.health import project_food_health
from ai_runtime.food.models import FOOD_EMERGENCY_ID, FoodPackage
from ai_runtime.food.planner import FoodPlanner, FoodUpdateProposal
from ai_runtime.food.store import (
    FoodCatalog,
    FoodCatalogRepository,
    validate_food_catalog_model_references,
)
from ai_runtime.models.model_reference import ModelReferenceError
from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.food_packages import (
    FoodPackageRepositoryError,
    SQLiteFoodPackageRepository,
)
from app.infrastructure.persistence.store import get_db


def stores(db_path: str) -> tuple[FoodCatalogRepository, dict[str, Any]]:
    return SQLiteFoodPackageRepository(db_path), query_model_evidence()


def set_lifecycle(
    repository: FoodCatalogRepository,
    food_id: str,
    *,
    enabled: bool,
    archived: bool | None = None,
) -> dict[str, Any]:
    evidence = query_model_evidence()
    package = require_package(repository.load(), food_id)
    if package.archived and enabled:
        raise HTTPException(status_code=409, detail="归档粮食必须先恢复")
    if enabled and package.primary is None:
        raise HTTPException(status_code=422, detail="主要模型不能为空")
    updated = replace(
        package,
        enabled=enabled,
        archived=package.archived if archived is None else archived,
    )
    persist_checked(repository, updated, evidence)
    return package_view(updated, evidence)


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
        "enabled": _strict_bool(body, "enabled", default_enabled),
        "archived": archived,
        "visibility_mode": str(body.get("visibility_mode") or "global"),
        "visible_user_ids": body.get("visible_user_ids", []),
        "roles": body.get("roles", {}),
    }
    try:
        return FoodPackage.from_dict(food_id, payload)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def persist_checked(
    repository: FoodCatalogRepository,
    package: FoodPackage,
    evidence: dict[str, Any],
    *,
    create: bool = False,
) -> FoodPackage:
    for reference in package.model_references:
        item = evidence.get(reference)
        if item is None or not item.is_fresh():
            raise HTTPException(
                status_code=422,
                detail=f"模型 {reference} 最近没有验证通过",
            )
    try:
        validate_food_catalog_model_references(
            FoodCatalog(packages={package.key: package})
        )
        return repository.create(package) if create else repository.update(package)
    except (FoodPackageRepositoryError, ModelReferenceError, ValueError) as error:
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


def build_generation_proposal(
    package: FoodPackage,
    body: dict[str, Any],
    evidence: dict[str, Any],
) -> FoodUpdateProposal:
    raw_scope = body.get("connection_ids", [])
    if not isinstance(raw_scope, list) or any(
        not isinstance(item, str) for item in raw_scope
    ):
        raise HTTPException(status_code=422, detail="connection_ids 必须是字符串数组")
    local_first = _strict_bool(body, "local_first", package.key == FOOD_EMERGENCY_ID)
    allow_remote = _strict_bool(body, "allow_remote", package.key != FOOD_EMERGENCY_ID)
    if not raw_scope:
        raise HTTPException(status_code=422, detail="至少选择一个生成来源")
    return FoodPlanner().propose_package(
        package,
        tuple(evidence.values()),
        connection_ids=tuple(raw_scope),
        local_first=local_first,
        allow_remote=allow_remote,
    )


def generation_preview_view(
    food_id: str | None,
    proposal: FoodUpdateProposal,
) -> dict[str, Any]:
    candidate = proposal.package.to_dict()
    candidate.pop("key", None)
    candidate.pop("system_role", None)
    candidate.pop("archived", None)
    return {
        "food_id": food_id,
        "candidate": candidate,
        "changes": [
            {
                "role": item.role,
                "old_model": item.old_model,
                "new_model": item.new_model,
            }
            for item in proposal.changes
        ],
        "warnings": list(proposal.warnings),
        "has_changes": proposal.has_changes,
    }


def validated_user_ids(request: Request, body: dict[str, Any]) -> tuple[int, ...]:
    raw_user_ids = body.get("visible_user_ids", [])
    if not isinstance(raw_user_ids, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in raw_user_ids
    ):
        raise HTTPException(status_code=422, detail="visible_user_ids 必须是整数数组")
    user_ids = tuple(sorted(set(raw_user_ids)))
    with get_db(request.app.state.db_path) as connection:
        available = {
            item.user_id for item in AccountRepository(connection).list_non_owner_users()
        }
    unknown = sorted(set(user_ids) - available)
    if unknown:
        raise HTTPException(status_code=422, detail="可见范围包含不存在的用户")
    return user_ids


def normalize_visibility(
    request: Request,
    body: dict[str, Any],
    *,
    system: bool,
    existing: FoodPackage | None = None,
) -> dict[str, Any]:
    mode = str(
        body.get(
            "visibility_mode",
            existing.visibility_mode if existing is not None else "global",
        )
        or "global"
    )
    ids = (
        list(existing.visible_user_ids)
        if "visible_user_ids" not in body and existing is not None
        else body.get("visible_user_ids", [])
    )
    if system:
        if mode != "global" or ids:
            raise HTTPException(status_code=422, detail="系统粮食只能保持所有人可见")
        return {"visibility_mode": "global", "visible_user_ids": []}
    if mode not in {"global", "users"}:
        raise HTTPException(status_code=422, detail="visibility_mode 必须是 global 或 users")
    if not isinstance(ids, list):
        raise HTTPException(status_code=422, detail="visible_user_ids 必须是整数数组")
    if mode == "global" and ids:
        raise HTTPException(status_code=422, detail="全局可见不能选择指定用户")
    if mode == "users":
        if not ids:
            raise HTTPException(status_code=422, detail="指定用户可见至少需要一个用户")
        ids = list(validated_user_ids(request, {"visible_user_ids": ids}))
    return {"visibility_mode": mode, "visible_user_ids": ids}


def _strict_bool(body: dict[str, Any], field: str, default: bool) -> bool:
    value = body.get(field, default)
    if not isinstance(value, bool):
        raise HTTPException(status_code=422, detail=f"{field} 必须是布尔值")
    return value


__all__ = (
    "catalog_view",
    "build_generation_proposal",
    "generation_preview_view",
    "new_food_key",
    "normalize_visibility",
    "package_view",
    "parse_package",
    "persist_checked",
    "require_package",
    "set_lifecycle",
    "stores",
)
