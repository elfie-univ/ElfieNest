from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from devtools.nest_lab.app import create_app
from devtools.nest_lab.event_log import LabEventLog


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(tmp_path), base_url="http://127.0.0.1")


def test_nest_lab_health_is_independent_from_production_service(tmp_path) -> None:
    # Given
    client = _client(tmp_path)

    # When
    response = client.get("/api/health")

    # Then
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "nest-lab",
        "scope": "developer",
        "production_engine": False,
        "runtime_startup_error": "",
    }


def test_nest_lab_keeps_http_surface_available_when_gateway_start_fails(
    monkeypatch, tmp_path
) -> None:
    def fail_gateway_start(_world) -> None:
        raise RuntimeError("Godot Runtime gateway failed to start: port unavailable")

    monkeypatch.setattr(
        "devtools.nest_lab.world.NestLabWorld.start", fail_gateway_start
    )

    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        response = client.get("/nest/experiment")
        health = client.get("/api/health")

    assert response.status_code == 200
    assert health.json()["status"] == "degraded"
    assert "port unavailable" in health.json()["runtime_startup_error"]


def test_nest_lab_root_shell_disables_browser_cache(tmp_path) -> None:
    # Given
    client = _client(tmp_path)

    # When
    response = client.get("/")

    # Then: a restarted Lab cannot display a cached shell from an older worktree.
    assert response.headers["cache-control"] == "no-store"


def test_nest_lab_exposes_world_module_status_without_user_auth(tmp_path) -> None:
    # Given
    client = _client(tmp_path)

    # When
    response = client.get("/api/world")

    # Then
    assert response.status_code == 200
    assert response.json()["module"] == "elfienest-world"
    assert Path(response.json()["data_dir"]) == tmp_path


def test_nest_lab_exposes_an_isolated_runtime_control_surface(tmp_path) -> None:
    # Given
    client = _client(tmp_path)

    # When
    response = client.get("/api/runtime")

    # Then
    assert response.status_code == 200
    assert response.json()["scope"] == "developer"
    assert response.json()["protocol"] == 3
    assert response.json()["websocket_url"].startswith("ws://127.0.0.1:")
    assert response.json()["nonce"]


def test_nest_lab_configures_beds_and_manages_lab_actors(tmp_path) -> None:
    # Given
    client = _client(tmp_path)

    # When
    world = client.put("/api/world", json={"bed_count": 2})
    fox = client.post("/api/actors", json={"species": "fox"})
    dog = client.post("/api/actors", json={"species": "dog"})

    # Then
    assert world.status_code == 200
    assert world.json()["bed_count"] == 2
    assert fox.status_code == 201
    assert dog.status_code == 201
    assert [
        actor["species"] for actor in client.get("/api/actors").json()["items"]
    ] == [
        "fox",
        "dog",
    ]


def test_nest_lab_rejects_shrinking_below_current_actor_count(tmp_path) -> None:
    # Given
    client = _client(tmp_path)
    client.put("/api/world", json={"bed_count": 2})
    client.post("/api/actors", json={"species": "fox"})
    client.post("/api/actors", json={"species": "dog"})

    # When
    response = client.put("/api/world", json={"bed_count": 1})

    # Then
    assert response.status_code == 409
    assert response.json()["detail"] == "床位数不能小于当前角色数量"


def test_nest_lab_controls_wander_pause_resume_and_reset(tmp_path) -> None:
    # Given
    client = _client(tmp_path)

    # When
    wander = client.post("/api/simulation/wander")
    paused = client.post("/api/simulation/pause")
    resumed = client.post("/api/simulation/resume")
    reset = client.post("/api/simulation/reset")

    # Then
    assert wander.json()["wandering"] is True
    assert paused.json()["paused"] is True
    assert resumed.json()["paused"] is False
    assert reset.json()["actor_count"] == 0
    assert reset.json()["world_revision"] > 1


def test_nest_lab_events_expose_an_observed_time_and_human_context() -> None:
    # Given
    events = LabEventLog()

    # When
    events.append("gateway_started", "ws://127.0.0.1:8891")

    # Then
    event = events.items()[0].to_dict()
    assert event["name"] == "gateway_started"
    assert event["detail"]
    assert event["occurred_at"].endswith("+00:00")
