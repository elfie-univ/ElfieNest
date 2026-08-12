"""Elfie Lab 的隔离 Runtime 状态与最小配置路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from devtools.elfie_lab.api_models import ConfigureFoodRequest
from devtools.elfie_lab.food_status import build_food_items
from devtools.elfie_lab.runtime_foods import ElfieLabRuntime
from elfie.brain.food_port import FoodPort


def build_system_router(
    runtime: ElfieLabRuntime,
    food_store: FoodPort,
    *,
    developer_runtime: bool,
) -> APIRouter:
    """Expose only the Lab-local status, Food list and setup action."""
    router = APIRouter()

    @router.get("/api/runtime/status")
    def runtime_status() -> dict[str, object]:
        status = runtime.status()
        status["scope"] = "developer" if developer_runtime else "override"
        return status

    @router.get("/api/runtime/foods")
    def runtime_foods() -> dict[str, object]:
        """Read Foods and local model choices without probing a model."""
        try:
            items = build_food_items(runtime, food_store)
            local_models = runtime.local_models()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {"items": items, "local_models": local_models}

    @router.post("/api/runtime/foods/configure")
    def configure_food(request: ConfigureFoodRequest) -> dict[str, object]:
        try:
            selected_food = runtime.configure(
                mode=request.mode,
                model=request.model,
                api_base=request.api_base or "",
                api_key=request.api_key or "",
                alias=request.alias or "",
            )
            return {
                "items": build_food_items(runtime, food_store),
                "local_models": runtime.local_models(),
                "selected_food": selected_food,
            }
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (OSError, RuntimeError) as error:
            raise HTTPException(status_code=503, detail="测试粮食保存失败") from error

    return router
