from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.configuration.settings import (
    SettingsService,
    StoredElfieSettings,
    StoredLoginRateLimit,
    StoredRuntimeSettings,
    StoredSecuritySettings,
)
from app.interfaces.api.v1.admin.settings import router
from app.interfaces.api.v1.auth import require_manager


class MemorySettingsStore:
    def __init__(self) -> None:
        self.elfies = StoredElfieSettings(
            max_elfies_per_user=3,
            personality_presets_enabled=(
                ("活泼好动", True),
                ("安静温顺", True),
            ),
        )
        self.runtime = StoredRuntimeSettings(tick_interval_sec=1.5)
        self.security = StoredSecuritySettings(
            session_ttl_days=7,
            rate_limit=StoredLoginRateLimit(max_attempts=5, window_seconds=300),
        )

    def load_elfie_settings(self) -> StoredElfieSettings:
        return self.elfies

    def save_elfie_settings(self, settings: StoredElfieSettings) -> None:
        self.elfies = settings

    def load_runtime_settings(self) -> StoredRuntimeSettings:
        return self.runtime

    def save_runtime_settings(self, settings: StoredRuntimeSettings) -> None:
        self.runtime = settings

    def load_security_settings(self) -> StoredSecuritySettings:
        return self.security

    def save_security_settings(self, settings: StoredSecuritySettings) -> None:
        self.security = settings


def _manager() -> AccountPrincipal:
    return AccountPrincipal(
        user_id=1,
        account_id="owner",
        role="owner",
        default_landing_page="manage",
    )


def _client() -> TestClient:
    app = FastAPI()
    app.state.settings = SettingsService(MemorySettingsStore())
    app.dependency_overrides[require_manager] = _manager
    app.include_router(router)
    return TestClient(app)


def test_resources_are_explicit_and_return_strict_shapes() -> None:
    with _client() as client:
        elfies = client.get("/api/v1/admin/settings/elfies")
        runtime = client.get("/api/v1/admin/settings/runtime")
        security = client.get("/api/v1/admin/settings/security")

    assert elfies.status_code == 200
    assert elfies.json() == {
        "max_elfies_per_user": 3,
        "personality_presets_enabled": {
            "活泼好动": True,
            "安静温顺": True,
        },
    }
    assert runtime.json() == {"tick_interval_sec": 1.5}
    assert security.json()["rate_limit"] == {
        "max_attempts": 5,
        "window_seconds": 300,
    }


def test_patch_updates_only_supplied_fields() -> None:
    with _client() as client:
        response = client.patch(
            "/api/v1/admin/settings/elfies",
            json={"max_elfies_per_user": 4},
        )

    assert response.status_code == 200
    assert response.json()["max_elfies_per_user"] == 4
    assert "allowed_species_ids" not in response.json()


def test_unknown_and_null_fields_are_rejected() -> None:
    with _client() as client:
        unknown = client.patch(
            "/api/v1/admin/settings/runtime",
            json={"unknown": 1},
        )
        retired_species_field = client.patch(
            "/api/v1/admin/settings/elfies",
            json={"allowed_species_ids": ["fox"]},
        )
        null_value = client.patch(
            "/api/v1/admin/settings/security",
            json={"session_ttl_days": None},
        )

    assert unknown.status_code == 422
    assert retired_species_field.status_code == 422
    assert null_value.status_code == 422


def test_no_generic_section_route_is_defined() -> None:
    paths = {route.path for route in router.routes}

    assert paths == {
        "/api/v1/admin/settings/elfies",
        "/api/v1/admin/settings/runtime",
        "/api/v1/admin/settings/security",
    }
