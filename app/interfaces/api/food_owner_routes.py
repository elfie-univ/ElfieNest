"""Owner APIs for the database-backed food strategy catalog."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.food.models import SYSTEM_FOOD_IDS, FoodPackage
from app.infrastructure.persistence.food_packages import (
    FoodPackageRepositoryError,
    SQLiteFoodPackageRepository,
)
from app.interfaces.api.food_catalog_support import (
    build_generation_proposal as _build_generation_proposal,
)
from app.interfaces.api.food_catalog_support import (
    catalog_view as _catalog_view,
)
from app.interfaces.api.food_catalog_support import (
    generation_preview_view as _generation_preview_view,
)
from app.interfaces.api.food_catalog_support import (
    new_food_key as _new_food_key,
)
from app.interfaces.api.food_catalog_support import (
    normalize_visibility as _normalize_visibility,
)
from app.interfaces.api.food_catalog_support import (
    package_view as _package_view,
)
from app.interfaces.api.food_catalog_support import (
    parse_package as _parse_package,
)
from app.interfaces.api.food_catalog_support import (
    persist_checked as _persist_checked,
)
from app.interfaces.api.food_catalog_support import (
    require_package as _require_package,
)
from app.interfaces.api.food_catalog_support import (
    set_lifecycle as _set_lifecycle,
)
from app.interfaces.api.food_catalog_support import (
    stores as _stores,
)
from app.interfaces.api.v1.auth import require_manager

router = APIRouter(
    prefix="/api/owner/runtime/foods",
    tags=["runtime-foods"],
)


@router.get("/")
async def list_foods(
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    repository, evidence = _stores(request.app.state.db_path)
    return _catalog_view(repository.load(), evidence)


@router.post("/", status_code=201)
async def create_food(
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    repository, evidence = _stores(request.app.state.db_path)
    current = repository.load()
    display_name = str(body.get("display_name") or "").strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="粮食名称不能为空")
    key = _new_food_key(current)
    visibility = _normalize_visibility(request, body, system=False)
    payload = {**body, **visibility}
    package = _parse_package(
        key,
        payload,
        default_enabled=False,
        system_role=None,
        archived=False,
    )
    if package.primary is None:
        raise HTTPException(status_code=422, detail="主要模型不能为空")
    saved = _persist_checked(repository, package, evidence, create=True)
    catalog = repository.load()
    return {
        "food": _package_view(saved, evidence),
        "catalog": _catalog_view(catalog, evidence),
    }


@router.post("/generation-preview")
async def preview_new_food_generation(
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    repository, evidence = _stores(request.app.state.db_path)
    display_name = str(body.get("display_name") or "").strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="粮食名称不能为空")
    visibility = _normalize_visibility(request, body, system=False)
    seed = FoodPackage(
        "food_preview",
        display_name,
        enabled=False,
        visibility_mode=visibility["visibility_mode"],
        visible_user_ids=tuple(visibility["visible_user_ids"]),
    )
    proposal = _build_generation_proposal(seed, body, evidence)
    return _generation_preview_view(None, proposal)


@router.put("/{food_id}")
async def edit_food(
    food_id: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    repository, evidence = _stores(request.app.state.db_path)
    current = repository.load()
    existing = _require_package(current, food_id)
    visibility = _normalize_visibility(
        request,
        body,
        system=existing.system_role is not None,
        existing=existing,
    )
    payload = {
        "display_name": body.get("display_name", existing.display_name),
        "enabled": body.get("enabled", existing.enabled),
        "roles": body.get("roles", existing.to_dict()["roles"]),
        **visibility,
    }
    package = _parse_package(
        food_id,
        payload,
        default_enabled=existing.enabled,
        system_role=existing.system_role,
        archived=existing.archived,
    )
    saved = _persist_checked(repository, package, evidence)
    return {"food": _package_view(saved, evidence), "warnings": []}


@router.post("/{food_id}/generation-preview")
async def preview_food_generation(
    food_id: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    repository, evidence = _stores(request.app.state.db_path)
    package = _require_package(repository.load(), food_id)
    visibility = _normalize_visibility(
        request,
        body,
        system=package.system_role is not None,
        existing=package,
    )
    seed = replace(
        package,
        visibility_mode=visibility["visibility_mode"],
        visible_user_ids=tuple(visibility["visible_user_ids"]),
    )
    proposal = _build_generation_proposal(seed, body, evidence)
    return _generation_preview_view(food_id, proposal)


@router.post("/{food_id}/enable")
async def enable_food(
    food_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    return _set_lifecycle(
        SQLiteFoodPackageRepository(request.app.state.db_path),
        food_id,
        enabled=True,
        archived=False,
    )


@router.post("/{food_id}/disable")
async def disable_food(
    food_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    return _set_lifecycle(
        SQLiteFoodPackageRepository(request.app.state.db_path),
        food_id,
        enabled=False,
    )


@router.post("/{food_id}/archive")
async def archive_food(
    food_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    if food_id in SYSTEM_FOOD_IDS:
        raise HTTPException(status_code=409, detail="系统粮食不能归档")
    return _set_lifecycle(
        SQLiteFoodPackageRepository(request.app.state.db_path),
        food_id,
        enabled=False,
        archived=True,
    )


@router.post("/{food_id}/restore")
async def restore_food(
    food_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    if food_id in SYSTEM_FOOD_IDS:
        raise HTTPException(status_code=409, detail="系统粮食不能恢复")
    return _set_lifecycle(
        SQLiteFoodPackageRepository(request.app.state.db_path),
        food_id,
        enabled=False,
        archived=False,
    )


@router.delete("/{food_id}")
async def delete_food(
    food_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    if food_id in SYSTEM_FOOD_IDS:
        raise HTTPException(status_code=409, detail="系统粮食不能删除")
    repository, evidence = _stores(request.app.state.db_path)
    try:
        repository.delete(food_id)
    except FoodPackageRepositoryError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _catalog_view(repository.load(), evidence)


__all__ = ("router",)
