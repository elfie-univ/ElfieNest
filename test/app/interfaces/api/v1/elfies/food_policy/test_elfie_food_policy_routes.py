from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.configuration.food import (
    ElfieFoodOptionResult,
    FoodService,
    MainFoodPolicyResult,
)
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.elfies.food_policy import router


def _principal() -> AccountPrincipal:
    return AccountPrincipal(7, "member", "user", "/chat")


class StubFoodService(FoodService):
    def __init__(self) -> None:
        self.updated: tuple[str, str] | None = None

    def get_elfie_policy(self, principal, query):
        _ = principal
        return _policy(query.elfie_id, "")

    def update_elfie_policy(self, principal, command):
        _ = principal
        self.updated = (command.elfie_id, command.main_food_id)
        return _policy(command.elfie_id, command.main_food_id)


def _policy(elfie_id: str, selected: str) -> MainFoodPolicyResult:
    _ = elfie_id
    return MainFoodPolicyResult(
        main_food_id=selected,
        effective_main_food_id=selected or "food_common",
        main_food_options=(ElfieFoodOptionResult("food_common", "Common"),),
        main_food_unavailable=False,
    )


def test_member_food_policy_uses_elfie_resource_and_forbids_extra_fields() -> None:
    app = FastAPI()
    service = StubFoodService()
    app.state.food = service
    app.include_router(router)
    app.dependency_overrides[require_user] = _principal
    client = TestClient(app)

    response = client.get("/api/v1/elfies/00000001/food-policy")
    assert response.status_code == 200
    assert response.json()["effective_main_food_id"] == "food_common"

    updated = client.put(
        "/api/v1/elfies/00000001/food-policy",
        json={"main_food_id": "food_common"},
    )
    assert updated.status_code == 200
    assert service.updated == ("00000001", "food_common")

    rejected = client.put(
        "/api/v1/elfies/00000001/food-policy",
        json={"main_food_id": "food_common", "user_id": 99},
    )
    assert rejected.status_code == 422
