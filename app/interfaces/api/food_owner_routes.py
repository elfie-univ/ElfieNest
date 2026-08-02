"""Owner APIs for stable food packages."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.food.evidence import query_model_evidence
from ai_runtime.food.models import (
    FOOD_EMERGENCY_ID,
    SYSTEM_FOOD_IDS,
)
from ai_runtime.food.planner import FoodPlanner
from ai_runtime.food.store import FoodCatalogStore
from app.features.accounts.auth import require_owner
from app.infrastructure.persistence.food_assignments import food_assignment_usage
from app.interfaces.api.food_catalog_support import (
    catalog_view as _catalog_view,
)
from app.interfaces.api.food_catalog_support import (
    new_food_key as _new_food_key,
)
from app.interfaces.api.food_catalog_support import (
    package_view as _package_view,
)
from app.interfaces.api.food_catalog_support import (
    parse_package as _parse_package,
)
from app.interfaces.api.food_catalog_support import (
    require_package as _require_package,
)
from app.interfaces.api.food_catalog_support import (
    save_checked as _save_checked,
)
from app.interfaces.api.food_catalog_support import (
    set_lifecycle as _set_lifecycle,
)
from app.interfaces.api.food_visibility_routes import router as food_visibility_router

router = APIRouter(
    prefix="/api/owner/runtime/foods",
    tags=["runtime-foods"],
)
router.include_router(food_visibility_router)


def _stores() -> tuple[FoodCatalogStore, dict[str, Any]]:
    return FoodCatalogStore(), query_model_evidence()


@router.get("/")
async def list_foods(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store, evidence = _stores()
    return _catalog_view(store.load(), evidence)


@router.post("/", status_code=201)
async def create_food(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store, evidence = _stores()
    current = store.load()
    key = _new_food_key(current)
    package = _parse_package(key, body, default_enabled=False)
    updated = replace(
        current,
        packages={**current.packages, key: package},
    )
    _save_checked(store, updated, evidence)
    return {
        "food": _package_view(package, evidence),
        "catalog": _catalog_view(updated, evidence),
    }


@router.put("/{food_id}")
async def edit_food(
    food_id: str,
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store, evidence = _stores()
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
    _save_checked(store, updated, evidence)
    return {"food": _package_view(package, evidence), "warnings": []}


@router.post("/{food_id}/generation-preview")
async def preview_food_generation(
    food_id: str,
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store, evidence = _stores()
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
        tuple(evidence.values()),
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
    store, evidence = _stores()
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
    return _catalog_view(updated, evidence)


@router.post("/rollback")
async def rollback_foods(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    if body.get("confirm") is not True:
        raise HTTPException(status_code=409, detail="必须明确确认回滚")
    store, evidence = _stores()
    try:
        catalog = store.rollback_latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _catalog_view(catalog, evidence)
