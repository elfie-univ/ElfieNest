"""Loopback-only HTTP routes for Elfie Lab evaluation orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from devtools.elfie_lab import api_models
from devtools.elfie_lab.evaluation_batches import BatchEvaluationService
from devtools.elfie_lab.evaluation_models import LabEvaluationSuite
from devtools.elfie_lab.evaluation_presets import evaluation_presets
from devtools.elfie_lab.food_status import FoodStatusItem, find_food_item
from devtools.elfie_lab.model_execution_foods import ElfieLabModelEnvironment
from devtools.elfie_lab.reviewer_subscriptions import ReviewerSubscriptionStore
from devtools.elfie_lab.session_registry import SessionRegistry
from devtools.elfie_lab.storage import ElfieLabStorage


def _require_reviewer_subscription(
    subscription_id: str,
    requested_model: str,
    model_environment: ElfieLabModelEnvironment,
) -> tuple[dict[str, object], str]:
    """Resolve a reviewer model without touching the candidate Food catalog."""
    normalized = subscription_id.strip()
    # Offline tests use a deliberately explicit mock reviewer; it is not
    # surfaced by the product UI and never resolves through a Food package.
    if normalized == "mock":
        return {
            "id": "mock",
            "display_name": "测试评审模型",
            "api_base": "",
            "api_key": "",
            "models": ["elfie-mock"],
            "model": f"ollama/{requested_model.strip() or 'elfie-mock'}",
        }, f"ollama/{requested_model.strip() or 'elfie-mock'}"
    descriptor = ReviewerSubscriptionStore(model_environment.root).descriptor(
        normalized,
        requested_model,
    )
    return descriptor, str(descriptor["model"])


def build_evaluation_router(
    *,
    storage: ElfieLabStorage,
    sessions: SessionRegistry,
    service: BatchEvaluationService,
    model_environment: ElfieLabModelEnvironment,
    food_store,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/evaluations/presets")
    def list_presets():
        return {
            "items": [item.model_dump(mode="json") for item in evaluation_presets()]
        }

    @router.get("/api/evaluations/code-branches")
    def list_code_branches():
        return service.code_branches()

    @router.get("/api/evaluations")
    def list_batches(
        offset: int = 0,
        limit: int = 50,
        query: str = "",
        status: str = "",
        created_after: Optional[datetime] = None,
    ):
        if offset < 0 or limit < 1 or limit > 100:
            raise HTTPException(status_code=422, detail="分页参数无效")
        return service.list_batches(
            offset=offset,
            limit=limit,
            query=query,
            status=status,
            created_after=created_after,
        )

    @router.get("/api/evaluations/reports/{run_id}")
    def get_global_report(run_id: str):
        try:
            return service.get_report(run_id).public_payload()
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/api/evaluations/reports/{run_id}/evidence")
    def get_global_report_evidence(run_id: str):
        try:
            return service.evidence_payload(run_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/api/evaluations/batches/{batch_id}")
    def get_batch(batch_id: str):
        try:
            return service.batch_payload(batch_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post("/api/evaluations/batches/single", status_code=202)
    def start_single_batch(request: api_models.CreateSingleEvaluationBatchRequest):
        try:
            spec = storage.get_elfie(request.elfie_id)
            candidate = _require_ready_food(
                request.food_key,
                model_environment,
                food_store,
            )
            judge, judge_model = _require_reviewer_subscription(
                request.judge_subscription_id,
                request.judge_model,
                model_environment,
            )
            batch = service.start_single_batch(
                spec=spec,
                session=sessions.get(spec.elfie_id),
                suite=LabEvaluationSuite(request.suite),
                food_key=request.food_key.lower().strip(),
                judge_subscription_id=request.judge_subscription_id.lower().strip(),
                food_descriptor=candidate,
                judge_subscription_descriptor=judge,
                title=request.title.strip() or request.purpose.strip(),
                purpose=request.purpose.strip(),
                judge_model=judge_model,
            )
            return service.batch_payload(batch.batch_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/evaluations/batches/paired", status_code=202)
    def start_paired_batch(request: api_models.CreatePairedEvaluationBatchRequest):
        try:
            spec = storage.get_elfie(request.elfie_id)
            if request.food_key_b is None:
                raise ValueError("配对评测缺少共同粮食或粮食 B")
            food_b = _require_ready_food(
                request.food_key_b, model_environment, food_store
            )
            judge, judge_model = _require_reviewer_subscription(
                request.judge_subscription_id,
                request.judge_model,
                model_environment,
            )
            if request.comparison_variable == "food":
                if request.food_key_a is None:
                    raise ValueError("粮食对比缺少粮食 A")
                food_a = _require_ready_food(
                    request.food_key_a,
                    model_environment,
                    food_store,
                )
                batch = service.start_food_pair_batch(
                    spec=spec,
                    session=sessions.get(spec.elfie_id),
                    suite=LabEvaluationSuite(request.suite),
                    food_key_a=request.food_key_a.lower().strip(),
                    food_key_b=request.food_key_b.lower().strip(),
                    judge_subscription_id=request.judge_subscription_id.lower().strip(),
                    food_descriptor_a=food_a,
                    food_descriptor_b=food_b,
                    judge_subscription_descriptor=judge,
                    title=request.title.strip() or request.purpose.strip(),
                    purpose=request.purpose.strip(),
                    judge_model=judge_model,
                )
            else:
                batch = service.start_code_pair_batch(
                    spec=spec,
                    session=sessions.get(spec.elfie_id),
                    suite=LabEvaluationSuite(request.suite),
                    food_key=request.food_key_b.lower().strip(),
                    judge_subscription_id=request.judge_subscription_id.lower().strip(),
                    food_descriptor=food_b,
                    judge_subscription_descriptor=judge,
                    code_ref_a=request.code_ref_a or "",
                    code_ref_b=request.code_ref_b or "",
                    title=request.title.strip() or request.purpose.strip(),
                    purpose=request.purpose.strip(),
                    judge_model=judge_model,
                )
            return service.batch_payload(batch.batch_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/evaluations/comparisons")
    def compare_reports(request: api_models.CompareEvaluationReportsRequest):
        try:
            return service.compare_reports(
                request.report_a_id,
                request.report_b_id,
            ).model_dump(mode="json")
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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
            reviewer, judge_model = _require_reviewer_subscription(
                request.judge_subscription_id,
                request.judge_model,
                model_environment,
            )
            profile = sessions.get(elfie_id).profile()
            run = service.start_run(
                spec=spec,
                profile=profile,
                suite=LabEvaluationSuite(request.suite),
                food_key=request.food_key.lower().strip(),
                judge_subscription_id=request.judge_subscription_id.lower().strip(),
                food_descriptor=candidate_food,
                judge_subscription_descriptor=reviewer,
                judge_model=judge_model,
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
