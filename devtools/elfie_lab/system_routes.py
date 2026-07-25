"""Read-only development Runtime status routes for Elfie Lab."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_runtime.food.store import FoodCatalogStore
from devtools.elfie_lab.food_status import build_food_items
from devtools.runtime_lab import RuntimeLabConfigStore


def build_system_router(
    runtime_store: RuntimeLabConfigStore,
    food_store: FoodCatalogStore,
    configure_runtime_command: str,
    *,
    developer_runtime: bool,
) -> APIRouter:
    """Expose the Lab-local Runtime configuration without production endpoints."""
    router = APIRouter()

    @router.get("/api/runtime/status")
    def runtime_status() -> dict[str, object]:
        status = runtime_store.status()
        status["scope"] = "developer" if developer_runtime else "override"
        return status

    @router.get("/api/runtime/foods")
    def runtime_foods() -> dict[str, object]:
        """Read the food catalog used by this Lab's isolated Runtime root."""
        try:
            items = build_food_items(
                runtime_store,
                food_store,
                configure_runtime_command,
            )
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {
            "items": items,
            "configuration_command": configure_runtime_command,
        }

    return router
