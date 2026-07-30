"""Owner APIs for stable food packages."""

from __future__ import annotations

import secrets
from dataclasses import replace
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.health import project_food_health
from ai_runtime.food.models import (
    FOOD_EMERGENCY_ID,
    SYSTEM_FOOD_IDS,
    FoodPackage,
)
from ai_runtime.food.planner import FoodPlanner
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.models.model_reference import ModelReferenceError
from app.features.accounts.auth import require_owner
from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.food_assignments import (
    food_assignment_usage,
    list_food_access_users,
    replace_food_access_users,
)
from app.infrastructure.persistence.store import get_db

router = APIRouter(
    prefix="/api/owner/runtime/foods",
    tags=["runtime-foods"],
)


def _stores() -> tuple[FoodCatalogStore, ModelEvidenceStore]:
    return FoodCatalogStore(), ModelEvidenceStore()


@router.get("/")
async def list_foods(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store, evidence_store = _stores()
    return _catalog_view(store.load(), evidence_store.load())


@router.post("/", status_code=201)
async def create_food(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store, evidence_store = _stores()
    current = store.load()
    key = _new_food_key(current)
    package = _parse_package(key, body, default_enabled=False)
    updated = replace(
        current,
        packages={**current.packages, key: package},
    )
    _save_checked(store, updated, evidence_store.load())
    return {
        "food": _package_view(package, evidence_store.load()),
        "catalog": _catalog_view(updated, evidence_store.load()),
    }


@router.put("/{food_id}")
async def edit_food(
    food_id: str,
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store, evidence_store = _stores()
    current = store.load()
    existing = _require_package(current, food_id)
    package = _parse_package(
        food_id,
        body,
        default_enabled=existing.enabled,
        system_role=existing.system_role,
        archived=existing.archived,
    )
    updated = replace(
        current,
        packages={**current.packages, food_id: package},
    )
    evidence = evidence_store.load()
    _save_checked(store, updated, evidence)
    return {"food": _package_view(package, evidence), "warnings": []}


@router.post("/{food_id}/generation-preview")
async def preview_food_generation(
    food_id: str,
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store, evidence_store = _stores()
    package = _require_package(store.load(), food_id)
    raw_scope = body.get("connection_ids", [])
    if not isinstance(raw_scope, list) or any(
        not isinstance(item, str) for item in raw_scope
    ):
        raise HTTPException(status_code=422, detail="connection_ids 必须是字符串数组")
    local_first = bool(body.get("local_first", package.key == FOOD_EMERGENCY_ID))
    allow_remote = bool(body.get("allow_remote", package.key != FOOD_EMERGENCY_ID))
    proposal = FoodPlanner().propose_package(
        package,
        tuple(evidence_store.load().values()),
        connection_ids=tuple(raw_scope),
        local_first=local_first,
        allow_remote=allow_remote,
    )
    return {
        "food_id": food_id,
        "candidate": proposal.package.to_dict(),
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


@router.post("/{food_id}/enable")
async def enable_food(
    food_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    return _set_lifecycle(food_id, enabled=True, archived=False)


@router.post("/{food_id}/disable")
async def disable_food(
    food_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    return _set_lifecycle(food_id, enabled=False)


@router.post("/{food_id}/archive")
async def archive_food(
    food_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    if food_id in SYSTEM_FOOD_IDS:
        raise HTTPException(status_code=409, detail="系统粮食不能归档")
    return _set_lifecycle(food_id, enabled=False, archived=True)


@router.post("/{food_id}/restore")
async def restore_food(
    food_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    return _set_lifecycle(food_id, enabled=False, archived=False)


@router.delete("/{food_id}")
async def delete_food(
    food_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    if food_id in SYSTEM_FOOD_IDS:
        raise HTTPException(status_code=409, detail="系统粮食不能删除")
    store, evidence_store = _stores()
    current = store.load()
    package = _require_package(current, food_id)
    if not package.archived:
        raise HTTPException(status_code=409, detail="粮食必须先归档才能删除")
    usage = food_assignment_usage(request.app.state.db_path, food_id)
    if usage["users"] or usage["elfies"]:
        raise HTTPException(status_code=409, detail="粮食仍被用户或精灵引用")
    packages = dict(current.packages)
    del packages[food_id]
    updated = replace(current, packages=packages)
    store.save(updated)
    return _catalog_view(updated, evidence_store.load())


@router.get("/{food_id}/visibility")
async def get_food_visibility(
    food_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    _require_package(FoodCatalogStore().load(), food_id)
    system = food_id in SYSTEM_FOOD_IDS
    assigned = (
        set()
        if system
        else set(list_food_access_users(request.app.state.db_path, food_id))
    )
    with get_db(request.app.state.db_path) as connection:
        repo = AccountRepository(connection)
        users = repo.list_non_owner_users()
    return {
        "food_key": food_id,
        "global": system,
        "user_ids": [] if system else sorted(assigned),
        "users": [
            {
                "user_id": int(row["id"]),
                "display_name": str(row["nickname"] or row["username"]),
                "assigned": system or int(row["id"]) in assigned,
            }
            for row in users
        ],
    }


@router.put("/{food_id}/visibility")
async def edit_food_visibility(
    food_id: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    _require_package(FoodCatalogStore().load(), food_id)
    if food_id in SYSTEM_FOOD_IDS:
        raise HTTPException(status_code=409, detail="系统粮食始终对所有用户可见")
    raw_user_ids = body.get("user_ids")
    if not isinstance(raw_user_ids, list) or any(
        not isinstance(user_id, int) for user_id in raw_user_ids
    ):
        raise HTTPException(status_code=422, detail="user_ids 必须是整数数组")
    assigned = replace_food_access_users(
        request.app.state.db_path,
        food_id,
        raw_user_ids,
    )
    return {"food_key": food_id, "user_ids": list(assigned)}


@router.post("/rollback")
async def rollback_foods(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    if body.get("confirm") is not True:
        raise HTTPException(status_code=409, detail="必须明确确认回滚")
    store, evidence_store = _stores()
    try:
        catalog = store.rollback_latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _catalog_view(catalog, evidence_store.load())


def _set_lifecycle(
    food_id: str,
    *,
    enabled: bool,
    archived: bool | None = None,
) -> dict[str, Any]:
    store, evidence_store = _stores()
    current = store.load()
    package = _require_package(current, food_id)
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
    return _package_view(updated_package, evidence_store.load())


def _parse_package(
    food_id: str,
    body: Dict[str, Any],
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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _save_checked(
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
    except (ModelReferenceError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _catalog_view(
    catalog: FoodCatalog,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": catalog.version,
        "global_default_food_id": catalog.global_default_food_id,
        "global_emergency_food_id": catalog.global_emergency_food_id,
        "packages": [
            _package_view(package, evidence) for package in catalog.ordered_packages()
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


def _package_view(
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


def _require_package(catalog: FoodCatalog, food_id: str) -> FoodPackage:
    package = catalog.packages.get(food_id)
    if package is None:
        raise HTTPException(status_code=404, detail="未知粮食")
    return package


def _new_food_key(catalog: FoodCatalog) -> str:
    while True:
        candidate = f"food_{secrets.token_hex(4)}"
        if candidate not in catalog.packages:
            return candidate
