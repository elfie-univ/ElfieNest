from fastapi.testclient import TestClient

from devtools.elfie_lab.app import create_app


def test_app_create_elfie_and_chat(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    assert client.get("/api/health").json()["status"] == "ok"
    created = client.post(
        "/api/elfies",
        json={"name": "Web 测试精灵", "species_id": "dog"},
    )
    assert created.status_code == 201
    elfie_id = created.json()["elfie_id"]
    assert created.json()["profile"]["species_id"] == "dog"
    assert created.json()["profile"]["appearance"]["species_id"] == "dog"
    assert (tmp_path / "data" / "elfies" / elfie_id / "profile.yaml").is_file()

    turn = client.post(
        f"/api/elfies/{elfie_id}/turns",
        json={"message": "跟我打个招呼", "food_key": "mock"},
    )
    assert turn.status_code == 200
    payload = turn.json()
    assert payload["elfie_id"] == elfie_id
    assert payload["model_call"]["provider"] == "mock"

    restored = client.get(f"/api/elfies/{elfie_id}")
    assert len(restored.json()["turns"]) == 1


def test_app_lifespan_stops_registered_elfie_sessions(tmp_path):
    app = create_app(str(tmp_path / "data"), str(tmp_path / "runtime"))

    with TestClient(app) as client:
        created = client.post("/api/elfies", json={"name": "生命周期测试"}).json()
        session = app.state.sessions.get(created["elfie_id"])
        runtime = session.elfie._cognitive_runtime
        assert runtime is not None
        assert runtime.is_running is True

    assert runtime.is_running is False


def test_app_calls_ready_callback_during_lifespan_startup(tmp_path):
    # Given
    lifecycle_events = []
    app = create_app(
        str(tmp_path / "data"),
        str(tmp_path / "runtime"),
        on_ready=lambda: lifecycle_events.append("ready"),
    )
    assert lifecycle_events == []

    # When
    with TestClient(app):
        events_while_running = list(lifecycle_events)

    # Then
    assert events_while_running == ["ready"]


def test_app_rejects_empty_stimulus(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    created = client.post("/api/elfies", json={"name": "空刺激测试"}).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"message": "", "food_key": "mock"},
    )

    assert response.status_code == 422


def test_static_shell_has_three_columns_without_top_navigation(tmp_path, client_for):
    runtime_dir = tmp_path / "runtime"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    response = client.get("/")

    assert response.status_code == 200
    assert 'class="elfie-panel"' in response.text
    assert 'class="timeline-panel"' in response.text
    assert 'class="detail-panel is-closed"' in response.text
    assert 'id="foodSelect"' in response.text
    assert 'id="foodSetupList"' in response.text
    assert 'id="appearanceFrame"' in response.text
    assert 'id="personalityRadar"' in response.text
    assert 'id="relationGraph"' in response.text
    assert 'id="createSpecies"' in response.text
    assert 'id="createAnatomy"' not in response.text
    assert 'id="runtimeMode"' not in response.text
    assert "<nav" not in response.text
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "完整 Runtime Lab" in script.text
    styles = client.get("/static/styles.css")
    assert styles.status_code == 200
    assert "color-scheme: light" in styles.text

    runtime = client.get("/api/runtime/status")
    assert runtime.status_code == 200
    assert runtime.json()["scope"] == "override"
    assert runtime.json()["config_dir"] == str(runtime_dir)


def test_app_rejects_unknown_species_and_saves_portrait(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    invalid = client.post(
        "/api/elfies", json={"name": "未知物种", "species_id": "rabbit"}
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/elfies", json={"name": "头像测试", "species_id": "fox"}
    ).json()
    elfie_id = created["elfie_id"]
    png_header = "iVBORw0KGgo="
    saved = client.put(
        f"/api/elfies/{elfie_id}/portrait",
        json={"data_url": f"data:image/png;base64,{png_header}"},
    )
    assert saved.status_code == 200
    image = client.get(saved.json()["portrait_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
