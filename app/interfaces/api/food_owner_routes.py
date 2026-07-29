"""粮食目录管理 API；界面只需消费这些稳定契约。"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.advisor import LLMFoodPlanningAdvisor, select_planning_model
from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.models import FIXED_FOOD_KINDS, FoodRecipe, FoodValidationStatus
from ai_runtime.food.planner import FoodPlanner, validate_food_recipe
from ai_runtime.food.store import (
    FoodCatalog,
    FoodCatalogStore,
    fingerprint_source,
    validate_food_catalog_model_references,
)
from ai_runtime.models.model_reference import (
    ModelReferenceError,
    parse_model_reference,
)
from ai_runtime.providers.profiles import get_product, get_profile
from ai_runtime.storage.data_home import (
    get_food_catalog_path,
    get_food_history_dir,
    get_model_evidence_path,
)
from ai_runtime.storage.provider_connections import (
    ProviderConnectionStore,
    is_connection_id,
)
from app.features.accounts.auth import require_owner
from app.infrastructure.persistence.food_assignments import (
    food_assignment_usage,
    list_food_access_users,
    replace_food_access_users,
)
from app.infrastructure.persistence.store import get_db

router = APIRouter(prefix="/api/owner/runtime/foods", tags=["runtime-foods"])

_FOOD_CATALOG_PATH: Path = get_food_catalog_path()
_FOOD_HISTORY_DIR: Path = get_food_history_dir()
_MODEL_EVIDENCE_PATH: Path = get_model_evidence_path()


def _stores() -> tuple[FoodCatalogStore, ModelEvidenceStore]:
    return (
        FoodCatalogStore(_FOOD_CATALOG_PATH, _FOOD_HISTORY_DIR),
        ModelEvidenceStore(_MODEL_EVIDENCE_PATH),
    )


@router.get("/")
async def list_foods(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    store, _evidence = _stores()
    return store.load().to_dict()


@router.post("/", status_code=201)
async def create_food(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    display_name = str(body.get("display_name") or "").strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="粮食套餐名称不能为空")
    store, evidence_store = _stores()
    current = store.load()
    food_key = _new_food_key(current)
    recipe_data = dict(body)
    recipe_data["source"] = "manual"
    recipe = _with_locality(FoodRecipe.from_dict(food_key, recipe_data))
    _require_explicit_model_references(FoodCatalog(recipes={food_key: recipe}))
    warnings = validate_food_recipe(recipe, list(evidence_store.load().values()))
    if warnings:
        recipe = FoodRecipe(
            **{
                **recipe.__dict__,
                "validation_status": FoodValidationStatus.WARNING,
            }
        )
    updated = FoodCatalog(
        version=current.version + 1,
        default_food=current.default_food or food_key,
        fallback_food=current.fallback_food,
        source_fingerprint=current.source_fingerprint,
        generation_sources=current.generation_sources,
        generation_note=current.generation_note,
        recipes={**current.recipes, food_key: recipe},
    )
    store.save(updated)
    return {
        "food": recipe.to_dict(),
        "warnings": warnings,
        "catalog": updated.to_dict(),
    }


@router.get("/update-status")
async def food_update_status(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    store, evidence_store = _stores()
    proposal = FoodPlanner().propose(list(evidence_store.load().values()), store.load())
    return {
        "update_available": proposal.has_changes,
        "change_count": sum(
            1 for change in proposal.changes if change.change_type != "unchanged"
        ),
        "warning_count": len(proposal.warnings),
    }


@router.post("/update-preview")
async def preview_food_update(
    body: Optional[Dict[str, Any]] = None,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    store, evidence_store = _stores()
    evidence = list(evidence_store.load().values())
    current = store.load()
    planner = FoodPlanner()
    if body is None or body.get("use_llm", True) is True:
        config = LLMRuntimeConfig.load()
        planning_model = select_planning_model(config, evidence)
        if planning_model:
            planner = FoodPlanner(LLMFoodPlanningAdvisor(config, planning_model))
    proposal = planner.propose(evidence, current)
    return _proposal_payload(proposal, current)


@router.post("/update-apply")
async def apply_food_update(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    if body.get("confirm") is not True:
        raise HTTPException(status_code=409, detail="必须明确确认粮食更新")
    store, evidence_store = _stores()
    raw_candidate = body.get("candidate")
    if not isinstance(raw_candidate, dict):
        raise HTTPException(status_code=422, detail="必须提交刚刚预览的粮食候选")
    current = store.load()
    submitted_base = str(body.get("base_catalog_fingerprint") or "")
    if submitted_base != fingerprint_source(current.to_dict()):
        raise HTTPException(
            status_code=409, detail="粮食候选已过期，请重新预览后再确认"
        )
    catalog = FoodCatalog.from_dict(raw_candidate)
    evidence = list(evidence_store.load().values())
    expected_fingerprint = (
        FoodPlanner().propose(evidence, current).catalog.source_fingerprint
    )
    if catalog.source_fingerprint != expected_fingerprint:
        raise HTTPException(
            status_code=409, detail="粮食候选已过期，请重新预览后再确认"
        )
    for recipe in catalog.recipes.values():
        warnings = validate_food_recipe(recipe, evidence)
        if warnings and recipe.validation_status is not FoodValidationStatus.FAILED:
            raise HTTPException(
                status_code=422,
                detail=f"{recipe.display_name} 未通过验证: {'; '.join(warnings)}",
            )
    _require_explicit_model_references(catalog)
    store.save(catalog)
    return {"applied": True, "candidate": catalog.to_dict()}


@router.put("/settings")
async def edit_food_settings(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    store, _evidence_store = _stores()
    current = store.load()
    default_food = str(body.get("default_food") or "").strip()
    fallback_food = str(body.get("fallback_food") or "").strip()
    if default_food not in current.recipes:
        raise HTTPException(status_code=422, detail="默认粮必须选择已有套餐")
    if fallback_food and fallback_food not in current.recipes:
        raise HTTPException(status_code=422, detail="保底粮必须选择已有套餐")
    updated = FoodCatalog(
        version=current.version + 1,
        default_food=default_food,
        fallback_food=fallback_food,
        source_fingerprint=current.source_fingerprint,
        generation_sources=current.generation_sources,
        generation_note=current.generation_note,
        recipes=current.recipes,
    )
    store.save(updated)
    warnings = (
        ["所选保底粮包含远程模型，断网时可能不可用"]
        if fallback_food and not current.recipes[fallback_food].local_only
        else []
    )
    return {"catalog": updated.to_dict(), "warnings": warnings}


@router.get("/{food_key}/visibility")
async def get_food_visibility(
    food_key: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    store, _evidence_store = _stores()
    if food_key not in store.load().recipes:
        raise HTTPException(status_code=404, detail="未知粮食")
    assigned = set(list_food_access_users(request.app.state.db_path, food_key))
    with get_db(request.app.state.db_path) as connection:
        users = connection.execute(
            """
            SELECT id, username, nickname
            FROM users
            WHERE role = 'user'
            ORDER BY id
            """
        ).fetchall()
    return {
        "food_key": food_key,
        "user_ids": sorted(assigned),
        "users": [
            {
                "user_id": int(row["id"]),
                "display_name": str(row["nickname"] or row["username"]),
                "assigned": int(row["id"]) in assigned,
            }
            for row in users
        ],
    }


@router.put("/{food_key}/visibility")
async def edit_food_visibility(
    food_key: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    store, _evidence_store = _stores()
    if food_key not in store.load().recipes:
        raise HTTPException(status_code=404, detail="未知粮食")
    raw_user_ids = body.get("user_ids")
    if not isinstance(raw_user_ids, list) or any(
        not isinstance(user_id, int) for user_id in raw_user_ids
    ):
        raise HTTPException(status_code=422, detail="user_ids 必须是整数数组")
    user_ids = tuple(sorted(set(raw_user_ids)))
    if user_ids:
        placeholders = ",".join("?" for _ in user_ids)
        with get_db(request.app.state.db_path) as connection:
            found = {
                int(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM users WHERE id IN ({placeholders})",  # noqa: S608
                    user_ids,
                ).fetchall()
            }
        missing = set(user_ids) - found
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"用户不存在: {sorted(missing)}",
            )
    assigned = replace_food_access_users(
        request.app.state.db_path,
        food_key,
        user_ids,
    )
    return {"food_key": food_key, "user_ids": list(assigned)}


@router.put("/{food_key}")
async def edit_food(
    food_key: str,
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    store, evidence_store = _stores()
    current = store.load()
    if food_key not in FIXED_FOOD_KINDS and food_key not in current.recipes:
        raise HTTPException(status_code=404, detail="未知粮食")
    recipe_data = dict(body)
    recipe_data["source"] = "manual"
    recipe = _with_locality(FoodRecipe.from_dict(food_key, recipe_data))
    _require_explicit_model_references(FoodCatalog(recipes={food_key: recipe}))
    warnings = validate_food_recipe(recipe, list(evidence_store.load().values()))
    if warnings:
        recipe = FoodRecipe(
            **{
                **recipe.__dict__,
                "validation_status": FoodValidationStatus.WARNING,
            }
        )
    recipes = dict(current.recipes)
    recipes[food_key] = recipe
    updated = FoodCatalog(
        version=current.version + 1,
        default_food=current.default_food or food_key,
        fallback_food=current.fallback_food,
        source_fingerprint=current.source_fingerprint,
        generation_sources=current.generation_sources,
        generation_note=current.generation_note,
        recipes=recipes,
    )
    store.save(updated)
    return {"food": recipe.to_dict(), "warnings": warnings}


@router.delete("/{food_key}")
async def delete_food(
    food_key: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    store, _evidence_store = _stores()
    current = store.load()
    if food_key not in current.recipes:
        raise HTTPException(status_code=404, detail="未知粮食")
    if food_key in {current.default_food, current.fallback_food}:
        raise HTTPException(
            status_code=409,
            detail="默认粮或保底粮不能删除，请先修改全局选择",
        )
    usage = food_assignment_usage(request.app.state.db_path, food_key)
    if usage["users"] or usage["elfies"]:
        raise HTTPException(
            status_code=409,
            detail="套餐仍分配给用户或精灵，请先解除关系",
        )
    recipes = dict(current.recipes)
    del recipes[food_key]
    updated = FoodCatalog(
        version=current.version + 1,
        default_food=current.default_food,
        fallback_food=current.fallback_food,
        source_fingerprint=current.source_fingerprint,
        generation_sources=current.generation_sources,
        generation_note=current.generation_note,
        recipes=recipes,
    )
    store.save(updated)
    return updated.to_dict()


@router.post("/rollback")
async def rollback_foods(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    if body.get("confirm") is not True:
        raise HTTPException(status_code=409, detail="必须明确确认回滚")
    store, _evidence = _stores()
    try:
        catalog = store.rollback_latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return catalog.to_dict()


def _proposal_payload(proposal, current: FoodCatalog) -> Dict[str, Any]:
    return {
        "base_catalog_fingerprint": fingerprint_source(current.to_dict()),
        "has_changes": proposal.has_changes,
        "generation_sources": list(proposal.generation_sources),
        "advisor_error": proposal.advisor_error,
        "warnings": list(proposal.warnings),
        "changes": [
            {
                "food_key": change.food_key,
                "change_type": change.change_type,
                "old_model": change.old_model,
                "new_model": change.new_model,
                "warnings": list(change.warnings),
            }
            for change in proposal.changes
        ],
        "current": current.to_dict(),
        "candidate": proposal.catalog.to_dict(),
    }


def _require_explicit_model_references(catalog: FoodCatalog) -> None:
    try:
        validate_food_catalog_model_references(catalog)
    except ModelReferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _new_food_key(catalog: FoodCatalog) -> str:
    while True:
        candidate = f"food_{secrets.token_hex(6)}"
        if candidate not in catalog.recipes:
            return candidate


def _with_locality(recipe: FoodRecipe) -> FoodRecipe:
    profiles = [
        recipe.primary,
        recipe.deep,
        recipe.vision,
        recipe.verifier,
        *recipe.technical_fallbacks,
    ]
    configured = [profile for profile in profiles if profile and profile.model]
    local_only = bool(configured) and all(
        _model_reference_is_local(profile.model) for profile in configured
    )
    return FoodRecipe(**{**recipe.__dict__, "local_only": local_only})


def _model_reference_is_local(model: str) -> bool:
    try:
        connection_id = parse_model_reference(model).connection_id
    except ModelReferenceError:
        return False
    legacy_profile = get_profile(connection_id)
    if legacy_profile is not None:
        return legacy_profile.connection_method == "local"
    if not is_connection_id(connection_id):
        return False
    connection = ProviderConnectionStore().load().connections.get(connection_id)
    if connection is not None:
        profile = get_product(connection.catalog_id)
        return bool(profile and profile.connection_method == "local")
    return False
