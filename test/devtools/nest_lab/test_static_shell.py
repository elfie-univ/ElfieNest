from pathlib import Path

from fastapi.testclient import TestClient

from devtools.nest_lab.app import create_app


def test_nest_lab_shell_has_room_controls_and_event_timeline(tmp_path) -> None:
    # Given
    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")

    # When
    response = client.get("/")

    # Then
    assert response.status_code == 200
    assert 'id="roomPreview"' in response.text
    assert 'id="bedCount"' in response.text
    assert 'id="addFox"' in response.text
    assert 'id="addDog"' in response.text
    assert 'id="wanderToggle"' in response.text
    assert 'id="pauseSimulation"' in response.text
    assert 'id="resetSimulation"' in response.text
    assert 'id="eventTimeline"' in response.text
    assert '<script type="module" src="/static/app.js"></script>' in response.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_nest_lab_frontend_wires_the_runtime_nonce_and_loopback_url() -> None:
    app_script = (
        Path(__file__).parents[3] / "devtools" / "nest_lab" / "static" / "app.js"
    ).read_text(encoding="utf-8")

    assert (
        "new URLSearchParams({\n"
        "    ws: runtime.websocket_url,\n"
        "    nonce: runtime.nonce,\n"
        '    mode: "nest_lab",\n'
        "  })" in app_script
    )
    assert "frame.src = `${status.entry_url}?${query.toString()}`" in app_script
