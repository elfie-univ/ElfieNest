from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from devtools.nest_lab.app import create_app


def test_nest_lab_health_is_independent_from_production_service(tmp_path) -> None:
    # Given
    client = TestClient(create_app(tmp_path))

    # When
    response = client.get("/api/health")

    # Then
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "nest-lab",
        "scope": "developer",
        "production_engine": False,
    }


def test_nest_lab_exposes_world_module_status_without_user_auth(tmp_path) -> None:
    # Given
    client = TestClient(create_app(tmp_path))

    # When
    response = client.get("/api/world")

    # Then
    assert response.status_code == 200
    assert response.json()["module"] == "elfienest-world"
    assert Path(response.json()["data_dir"]) == tmp_path
