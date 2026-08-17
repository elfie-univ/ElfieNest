from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal, parse_account_role
from app.features.operations import (
    OperationsFacade,
    StoredActiveSession,
    StoredDatabaseBackup,
    StoredTableCount,
    StoredUsageStats,
)
from app.interfaces.api.service_access import ServiceAccessPolicy
from app.interfaces.api.v1.admin.runtime import router
from app.interfaces.api.v1.auth import require_manager, require_user
from infrastructure.models.model_execution_observations import (
    FallbackObservation,
    ModelExecutionEventStatus,
    ModelExecutionObserver,
    ToolCallObservation,
)
from infrastructure.models.model_execution_observer import (
    ModelExecutionObserverProjectionAdapter,
)


class UnusedDatabaseAdapter:
    def collect_usage_stats(self) -> StoredUsageStats:
        raise AssertionError("runtime status must not query the database")

    def list_active_sessions(self, limit: int) -> tuple[StoredActiveSession, ...]:
        raise AssertionError("runtime status must not query sessions")

    def list_table_counts(self) -> tuple[StoredTableCount, ...]:
        raise AssertionError("runtime status must not query tables")

    def backup_databases(self) -> StoredDatabaseBackup:
        raise AssertionError("GET status must not back up databases")

    def reset_databases(self) -> None:
        raise AssertionError("GET status must not reset databases")


class UnusedNetworkAccessProjection:
    def preferred_lan_address(self) -> str | None:
        raise AssertionError("runtime status must not query network access")

    def current_wifi_name(self) -> str | None:
        raise AssertionError("runtime status must not query WiFi")


class NamedNetworkAccessProjection:
    def preferred_lan_address(self) -> str | None:
        return "192.168.1.8"

    def current_wifi_name(self) -> str | None:
        return "Elfie Home"


def _principal(role: str) -> AccountPrincipal:
    assert role in {"owner", "admin", "user"}
    return AccountPrincipal(
        user_id=1,
        account_id="actor",
        role=parse_account_role(role),
        default_landing_page="manage",
    )


def _client(observer: ModelExecutionObserver, role: str) -> TestClient:
    app = FastAPI()
    database = UnusedDatabaseAdapter()
    app.state.operations = OperationsFacade(
        database,
        database,
        ModelExecutionObserverProjectionAdapter(observer),
        UnusedNetworkAccessProjection(),
    )
    app.dependency_overrides[require_user] = lambda: _principal(role)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolated_runtime_reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))


def test_manager_runtime_status_preserves_the_existing_projection() -> None:
    observer = ModelExecutionObserver()
    observer.record_tool_call(
        ToolCallObservation(
            tool_name="web_search",
            status=ModelExecutionEventStatus.OK,
            metadata={"query": "ElfieNest"},
        )
    )
    observer.record_fallback(
        FallbackObservation(
            from_model_key="remote_deep",
            from_provider="openai",
            to_model_key="local_fast",
            to_provider="ollama",
            reason="remote unavailable",
        )
    )

    with _client(observer, "owner") as client:
        response = client.get("/api/v1/admin/runtime/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "observer": {
            "event_count": 2,
            "last_event": {
                "event_type": "fallback",
                "status": "ok",
                "subject": "local_fast",
                "metadata": {
                    "from_model_key": "remote_deep",
                    "from_provider": "openai",
                    "to_provider": "ollama",
                    "reason": "remote unavailable",
                },
            },
        },
    }
    assert len(observer.snapshot()) == 2


def test_manager_runtime_status_includes_the_authoritative_lifecycle_projection() -> (
    None
):
    observer = ModelExecutionObserver()
    app = _client(observer, "owner").app
    app.state.runtime_projection = lambda: {
        "schema_version": 1,
        "instance_id": "instance",
        "generation": 3,
        "revision": 7,
        "tier": "core_ready",
        "phase": "core_ready",
        "subphase": "",
        "desired_target": "normal",
        "reached_target": "core",
        "components": [],
        "endpoints": [],
        "model_state": "degraded",
        "model_common_state": "ready",
        "model_emergency_state": "unavailable",
        "model_revision": 4,
        "failures": [],
        "timings": [{"phase": "core", "duration_ms": 12, "elapsed_ms": None}],
        "protocol_versions": ["runtime/1"],
    }

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/runtime/status")

    assert response.status_code == 200
    lifecycle = response.json()["lifecycle"]
    assert lifecycle["tier"] == "core_ready"
    assert lifecycle["model_emergency_state"] == "unavailable"
    assert lifecycle["timings"] == [{"phase": "core", "duration_ms": 12}]


def test_non_manager_receives_the_standard_error_envelope() -> None:
    with _client(ModelExecutionObserver(), "user") as client:
        response = client.get("/api/v1/admin/runtime/status")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "runtime_status_forbidden",
            "message": "Runtime status requires a manager",
            "details": {},
        }
    }


def test_missing_operations_composition_uses_the_standard_error_envelope() -> None:
    app = FastAPI()
    app.dependency_overrides[require_user] = lambda: _principal("owner")
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/runtime/status")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "runtime_status_unavailable",
            "message": "运行状态暂时不可用",
            "details": {},
        }
    }


def test_mobile_access_projects_the_existing_lan_bind_policy() -> None:
    app = FastAPI()
    app.state.mobile_access = ServiceAccessPolicy.create(
        "lan",
        15212,
        lan_addresses=("192.168.1.8",),
    )
    app.dependency_overrides[require_manager] = lambda: _principal("owner")
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/runtime/mobile-access")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "network_name": None,
        "urls": ["http://192.168.1.8:15212/"],
    }


def test_mobile_access_projects_the_current_wifi_name() -> None:
    app = FastAPI()
    database = UnusedDatabaseAdapter()
    app.state.operations = OperationsFacade(
        database,
        database,
        ModelExecutionObserverProjectionAdapter(ModelExecutionObserver()),
        NamedNetworkAccessProjection(),
    )
    app.state.mobile_access = ServiceAccessPolicy.create(
        "lan",
        15212,
        lan_addresses=("192.168.1.8",),
    )
    app.dependency_overrides[require_manager] = lambda: _principal("owner")
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/runtime/mobile-access")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "network_name": "Elfie Home",
        "urls": ["http://192.168.1.8:15212/"],
    }


def test_runtime_resource_defines_only_existing_read_only_queries() -> None:
    assert {(route.path, next(iter(route.methods))) for route in router.routes} == {
        ("/api/v1/admin/runtime/status", "GET"),
        ("/api/v1/admin/runtime/mobile-access", "GET"),
    }
