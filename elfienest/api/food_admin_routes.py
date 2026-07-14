"""粮食目录管理 API；界面只需消费这些稳定契约。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from runtime.config import LLMRuntimeConfig
from runtime.food.advisor import LLMFoodPlanningAdvisor, select_planning_model
from runtime.food.evidence import ModelEvidenceStore
from runtime.food.models import FIXED_FOOD_KINDS, FoodRecipe, FoodValidationStatus
from runtime.food.planner import FoodPlanner, validate_food_recipe
from runtime.food.store import FoodCatalog, FoodCatalogStore
from runtime.storage.data_home import (
    get_food_catalog_path,
    get_food_history_dir,
    get_model_evidence_path,
)

from .admin_routes import require_admin

router = APIRouter(prefix="/api/admin/runtime/foods", tags=["runtime-foods"])

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
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
    store, _evidence = _stores()
    return store.load().to_dict()


@router.get("/update-status")
async def food_update_status(
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
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
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
    store, evidence_store = _stores()
    evidence = list(evidence_store.load().values())
    planner = FoodPlanner()
    if body is None or body.get("use_llm", True) is True:
        config = LLMRuntimeConfig.load()
        planning_model = select_planning_model(config, evidence)
        if planning_model:
            planner = FoodPlanner(LLMFoodPlanningAdvisor(config, planning_model))
    proposal = planner.propose(evidence, store.load())
    return _proposal_payload(proposal)


@router.post("/update-apply")
async def apply_food_update(
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
    if body.get("confirm") is not True:
        raise HTTPException(status_code=409, detail="必须明确确认粮食更新")
    store, evidence_store = _stores()
    raw_candidate = body.get("candidate")
    if isinstance(raw_candidate, dict):
        catalog = FoodCatalog.from_dict(raw_candidate)
        evidence = list(evidence_store.load().values())
        expected_fingerprint = (
            FoodPlanner().propose(evidence, store.load()).catalog.source_fingerprint
        )
        if catalog.source_fingerprint != expected_fingerprint:
            raise HTTPException(
                status_code=409,
                detail="粮食候选已过期，请重新预览后再确认",
            )
        unknown_foods = set(catalog.recipes) - set(FIXED_FOOD_KINDS)
        if unknown_foods:
            raise HTTPException(status_code=422, detail="候选包含未知粮食")
        for recipe in catalog.recipes.values():
            warnings = validate_food_recipe(recipe, evidence)
            if warnings and recipe.validation_status is not FoodValidationStatus.FAILED:
                raise HTTPException(
                    status_code=422,
                    detail=f"{recipe.display_name} 未通过验证: {'; '.join(warnings)}",
                )
        store.save(catalog)
        return {"applied": True, "candidate": catalog.to_dict()}
    proposal = FoodPlanner().propose(list(evidence_store.load().values()), store.load())
    store.save(proposal.catalog)
    return _proposal_payload(proposal)


@router.put("/{food_key}")
async def edit_food(
    food_key: str,
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
    if food_key not in FIXED_FOOD_KINDS:
        raise HTTPException(status_code=404, detail="未知粮食")
    store, evidence_store = _stores()
    current = store.load()
    recipe_data = dict(body)
    recipe_data["source"] = "manual"
    recipe = FoodRecipe.from_dict(food_key, recipe_data)
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
        source_fingerprint=current.source_fingerprint,
        generation_sources=current.generation_sources,
        generation_note=current.generation_note,
        recipes=recipes,
    )
    store.save(updated)
    return {"food": recipe.to_dict(), "warnings": warnings}


@router.post("/rollback")
async def rollback_foods(
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
    if body.get("confirm") is not True:
        raise HTTPException(status_code=409, detail="必须明确确认回滚")
    store, _evidence = _stores()
    try:
        catalog = store.rollback_latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return catalog.to_dict()


def _proposal_payload(proposal) -> Dict[str, Any]:
    return {
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
        "candidate": proposal.catalog.to_dict(),
    }
