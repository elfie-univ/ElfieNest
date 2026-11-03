from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.configuration import SettingsService
from app.interfaces.api.v1.admin.settings import router
from app.interfaces.api.v1.auth import require_manager
from infrastructure.persistence.configuration.settings import RuntimeSettingsAdapter
from nest.public import LifePhase, Nest
from test.app.interfaces.api.v1.admin.settings.test_routes import _manager


def test_save_reload_and_live_nest_share_the_same_schedule(tmp_path):
    adapter = RuntimeSettingsAdapter(tmp_path / "configs" / "runtime.yaml")
    app = FastAPI()
    app.state.settings = SettingsService(
        adapter, now=lambda: datetime(2026, 6, 21, 23, tzinfo=timezone.utc)
    )
    app.dependency_overrides[require_manager] = _manager
    app.include_router(router)
    with TestClient(app) as client:
        initial = client.get("/api/v1/admin/settings/environment")
        assert initial.status_code == 200
        settings = initial.json()["settings"]
        assert settings["sunrise_time"] == "06:00"
        assert not adapter._config_path.exists()
        settings["rest_time"] = "22:30"
        saved = client.put(
            "/api/v1/admin/settings/environment", json={"settings": settings}
        )
        assert saved.status_code == 200
        assert (
            client.get("/api/v1/admin/settings/environment").json()["settings"]
            == settings
        )
        invalid = {**settings, "daylight_source": "local"}
        assert (
            client.put(
                "/api/v1/admin/settings/environment", json={"settings": invalid}
            ).status_code
            == 422
        )
        assert (
            client.get("/api/v1/admin/settings/environment").json()["settings"]
            == settings
        )
    restored = RuntimeSettingsAdapter(adapter._config_path).load_environment_settings()
    nest = Nest()
    nest.tick(
        0,
        local_time=datetime(2026, 6, 21, 23, tzinfo=timezone.utc),
        environment_schedule=restored,
    )
    assert nest.life_phase is LifePhase.NIGHT
    assert nest.desired_environment.quiet_mode
    assert adapter.load_runtime_settings().tick_interval_sec == 1.5


def test_environment_settings_still_require_manager_authority(tmp_path):
    import pytest

    from app.features.accounts import AccountPrincipal
    from app.features.configuration import (
        GetEnvironmentSettingsQuery,
        SettingsForbidden,
    )

    service = SettingsService(RuntimeSettingsAdapter(tmp_path / "runtime.yaml"))
    with pytest.raises(SettingsForbidden):
        service.get_environment_settings(
            AccountPrincipal(
                user_id=1, account_id="member", role="user", default_landing_page="chat"
            ),
            GetEnvironmentSettingsQuery(),
        )
