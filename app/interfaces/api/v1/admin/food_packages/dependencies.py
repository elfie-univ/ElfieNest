"""Injected Food service dependency for administrator routes."""

from fastapi import HTTPException, Request

from app.features.configuration import food


def food_service(request: Request) -> food.FoodService:
    service = getattr(request.app.state, "food", None)
    if not isinstance(service, food.FoodService):
        raise HTTPException(status_code=500, detail="Food service is not configured")
    return service


__all__ = ("food_service",)
