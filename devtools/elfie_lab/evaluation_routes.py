"""Loopback-only HTTP routes for Elfie Lab evaluation orchestration."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from devtools.elfie_lab import api_models
from devtools.elfie_lab.evaluation_models import LabEvaluationSuite
from devtools.elfie_lab.evaluation_presets import evaluation_presets
from devtools.elfie_lab.evaluation_service import EvaluationService
from devtools.elfie_lab.food_status import FoodStatusItem, find_food_item
from devtools.elfie_lab.model_execution_foods import ElfieLabModelEnvironment
from devtools.elfie_lab.session_registry import SessionRegistry
from devtools.elfie_lab.storage import ElfieLabStorage


def build_evaluation_router(
    *,
    storage: ElfieLabStorage,
    sessions: SessionRegistry,
    service: EvaluationService,
    model_environment: ElfieLabModelEnvironment,
    food_store,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/evaluations/presets")
    def list_presets():
        return {
            "items": [item.model_dump(mode="json") for item in evaluation_presets()]
        }

    @router.get("/api/elfies/{elfie_id}/evaluations")
    def list_runs(elfie_id: str):
        try:
            storage.get_elfie(elfie_id)
            return service.history(elfie_id).public_payload()
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/api/elfies/{elfie_id}/evaluations/{run_id}")
    def get_run(elfie_id: str, run_id: str):
        try:
            storage.get_elfie(elfie_id)
            return service.get_run(elfie_id, run_id).public_payload()
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post(
        "/api/elfies/{elfie_id}/evaluations",
        status_code=202,
    )
    def start_run(
        elfie_id: str,
        request: api_models.CreateEvaluationRunRequest,
    ):
        try:
            spec = storage.get_elfie(elfie_id)
            candidate_food = _require_ready_food(
                request.food_key,
                model_environment,
                food_store,
            )
            judge_food = _require_ready_food(
                request.judge_food_key,
                model_environment,
                food_store,
            )
            profile = sessions.get(elfie_id).profile()
            run = service.start_run(
                spec=spec,
                profile=profile,
                suite=LabEvaluationSuite(request.suite),
                food_key=request.food_key.lower().strip(),
                judge_food_key=request.judge_food_key.lower().strip(),
                food_descriptor=candidate_food,
                judge_food_descriptor=judge_food,
            )
            return run.public_payload()
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/elfies/{elfie_id}/evaluations/{run_id}/baseline")
    def set_baseline(elfie_id: str, run_id: str):
        try:
            storage.get_elfie(elfie_id)
            return service.set_baseline(elfie_id, run_id).public_payload()
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return router


def _require_ready_food(
    food_key: str,
    model_environment,
    food_store,
) -> FoodStatusItem:
    normalized = food_key.lower().strip()
    food = find_food_item(normalized, model_environment, food_store)
    if food is None:
        raise ValueError(f"Runtime 粮食目录中不存在粮食: {normalized}")
    if not food["ready_for_attempt"]:
        raise ValueError(
            f"粮食“{food['display_name']}”尚未配置：{food['unavailable_reason']}"
        )
    return food


__all__ = ("build_evaluation_router",)
