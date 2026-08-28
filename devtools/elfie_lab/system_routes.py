"""Elfie Lab 的隔离模型执行状态与最小配置路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from devtools.elfie_lab.api_models import (
    ConfigureFoodRequest,
    ProbeOllamaRequest,
    SaveReviewerSubscriptionRequest,
)
from devtools.elfie_lab.food_status import build_food_items
from devtools.elfie_lab.model_execution_foods import ElfieLabModelEnvironment
from devtools.elfie_lab.model_subscriptions import list_model_subscriptions
from devtools.elfie_lab.reviewer_subscriptions import ReviewerSubscriptionStore
from elfie.brain.reasoning.food_port import FoodPort


def build_system_router(
    model_environment: ElfieLabModelEnvironment,
    food_store: FoodPort,
    *,
    developer_scope: bool,
) -> APIRouter:
    """Expose Lab-local status, candidate Foods, and independent reviewer setup."""
    router = APIRouter()

    # Keep the established HTTP path as a compatibility protocol; only the
    # model-layer implementation terminology is being renamed here.
    @router.get("/api/runtime/status")
    def model_execution_status() -> dict[str, object]:
        status = model_environment.status()
        status["scope"] = "developer" if developer_scope else "override"
        return status

    @router.get("/api/runtime/foods")
    def model_execution_foods() -> dict[str, object]:
        """Read only configured Lab Foods without probing a model."""
        try:
            items = build_food_items(model_environment, food_store)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {"items": items}

    @router.get("/api/runtime/model-subscriptions")
    def model_subscriptions() -> dict[str, object]:
        """List shared subscriptions for Food and remote reviewer selection."""
        try:
            return {"items": list_model_subscriptions(model_environment.root)}
        except (OSError, RuntimeError, ValueError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get("/api/runtime/reviewer-subscriptions")
    def reviewer_subscriptions() -> dict[str, object]:
        """List independently configured remote reviewer subscriptions."""
        try:
            return {
                "items": ReviewerSubscriptionStore(model_environment.root).list_public()
            }
        except (OSError, RuntimeError, ValueError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.post("/api/runtime/reviewer-subscriptions")
    def save_reviewer_subscription(
        request: SaveReviewerSubscriptionRequest,
    ) -> dict[str, object]:
        try:
            store = ReviewerSubscriptionStore(model_environment.root)
            item = store.save(
                subscription_id=request.subscription_id,
                display_name=request.display_name,
                api_base=request.api_base,
                api_key=request.api_key,
                models=request.models,
            )
            return {"item": item, "items": store.list_public()}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (OSError, RuntimeError) as error:
            raise HTTPException(status_code=503, detail="评审订阅保存失败") from error

    @router.delete("/api/runtime/reviewer-subscriptions/{subscription_id}")
    def delete_reviewer_subscription(subscription_id: str) -> dict[str, object]:
        try:
            ReviewerSubscriptionStore(model_environment.root).delete(subscription_id)
            return {"deleted_subscription": subscription_id}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (OSError, RuntimeError) as error:
            raise HTTPException(status_code=503, detail="评审订阅删除失败") from error

    @router.post("/api/runtime/foods/configure")
    def configure_food(request: ConfigureFoodRequest) -> dict[str, object]:
        try:
            selected_food = model_environment.configure_food(
                food_id=request.food_id,
                subscription_id=request.subscription_id,
                subscription_name=request.subscription_name,
                connection_type=request.connection_type,
                display_name=request.display_name,
                api_base=request.api_base,
                api_key=request.api_key,
                models=request.models,
                primary_model=request.primary_model,
                reasoning_model=request.reasoning_model,
                vision_model=request.vision_model,
                tool_model=request.tool_model,
                fallback_model=request.fallback_model,
            )
            return {
                "items": build_food_items(model_environment, food_store),
                "selected_food": selected_food,
            }
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (OSError, RuntimeError) as error:
            raise HTTPException(status_code=503, detail="测试粮食保存失败") from error

    @router.post("/api/runtime/ollama/probe")
    def probe_ollama(request: ProbeOllamaRequest) -> dict[str, str]:
        try:
            return model_environment.probe_ollama(api_base=request.api_base)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (OSError, RuntimeError) as error:
            raise HTTPException(status_code=503, detail="Ollama 检测失败") from error

    @router.delete("/api/runtime/foods/{food_id}")
    def delete_food(food_id: str) -> dict[str, object]:
        try:
            deleted_food_id = model_environment.delete_food(food_id=food_id.strip())
            return {"deleted_food": deleted_food_id}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (OSError, RuntimeError) as error:
            raise HTTPException(status_code=503, detail="粮食删除失败") from error

    return router
