from pathlib import Path

from devtools.elfie_lab.app import create_unified_app


def test_unified_app_serves_all_three_same_origin_shells(
    tmp_path: Path,
    client_for,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "devtools.nest_lab.world.NestLabWorld.start", lambda _world: None
    )
    monkeypatch.setattr(
        "devtools.nest_lab.world.NestLabWorld.stop", lambda _world: None
    )

    client = client_for(
        create_unified_app(
            tmp_path / "developer",
            http_port=19001,
            godot_ws_port=19002,
        )
    )

    for path in ("/elfie/experiment", "/elfie/evaluations", "/nest/experiment"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'window.__ELFIENEST_LAB__ = "unified"' in response.text

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["service"] == "developer-tools"
