from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.configuration.food import (
    EligibleFoodModelResult,
    FoodCatalogResult,
    FoodPackageMutationResult,
    FoodPackageResult,
    FoodRolesResult,
    FoodService,
)
from app.interfaces.api.v1.admin.food_packages import router
from app.interfaces.api.v1.auth import require_user


def _principal() -> AccountPrincipal:
    return AccountPrincipal(1, "owner", "owner", "/manage")


def _food() -> FoodPackageResult:
    return FoodPackageResult(
        food_id="food_common",
        display_name="Common",
        system_role="common",
        enabled=False,
        archived=False,
        visibility_mode="global",
        visible_user_ids=(),
        roles=FoodRolesResult(None, None, None, None, None),
        health="disabled",
        locality="unknown",
        latest_evidence_at=None,
    )


def _catalog() -> FoodCatalogResult:
    return FoodCatalogResult(
        version=1,
        global_default_food_id="food_common",
        global_emergency_food_id="food_emergency",
        packages=(_food(),),
        eligible_models=(
            EligibleFoodModelResult("cloud/main", "Main", False, ("text",)),
        ),
    )


class StubFoodService(FoodService):
    def __init__(self) -> None:
        self.created = False

    def list_packages(self, principal, query):
        _ = principal, query
        return _catalog()

    def create_package(self, principal, command):
        _ = principal, command
        self.created = True
        return FoodPackageMutationResult(_food(), catalog=_catalog())


def _client() -> tuple[TestClient, StubFoodService]:
    app = FastAPI()
    service = StubFoodService()
    app.state.food = service
    app.include_router(router)
    app.dependency_overrides[require_user] = _principal
    return TestClient(app), service


def test_admin_food_routes_use_versioned_resource_and_strict_dtos() -> None:
    client, service = _client()

    response = client.get("/api/v1/admin/food-packages")
    assert response.status_code == 200
    assert response.json()["packages"][0]["key"] == "food_common"

    created = client.post(
        "/api/v1/admin/food-packages",
        json={
            "display_name": "Custom",
            "enabled": False,
            "roles": {
                "primary": None,
                "reasoning": None,
                "vision": None,
                "tool": None,
                "fallback": None,
            },
            "visibility_mode": "global",
            "visible_user_ids": [],
        },
    )
    assert created.status_code == 201
    assert service.created is True

    rejected = client.post(
        "/api/v1/admin/food-packages",
        json={
            "display_name": "Custom",
            "roles": {},
            "unexpected": True,
        },
    )
    assert rejected.status_code == 422
