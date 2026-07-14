from fastapi.testclient import TestClient

from devtools.elfie_lab.app import create_app
from devtools.runtime_lab import RuntimeLabConfigStore


def test_app_create_elfie_and_chat(tmp_path):
    client = TestClient(create_app(str(tmp_path)))

    assert client.get("/api/health").json()["status"] == "ok"
    created = client.post(
        "/api/elfies",
        json={"name": "Web 测试精灵", "anatomy_type": "quadruped"},
    )
    assert created.status_code == 201
    elfie_id = created.json()["elfie_id"]

    turn = client.post(
        f"/api/elfies/{elfie_id}/turns",
        json={"message": "跟我打个招呼", "mode": "mock"},
    )
    assert turn.status_code == 200
    payload = turn.json()
    assert payload["elfie_id"] == elfie_id
    assert payload["model_call"]["provider"] == "mock"

    restored = client.get(f"/api/elfies/{elfie_id}")
    assert len(restored.json()["turns"]) == 1


def test_app_rejects_empty_stimulus(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    created = client.post("/api/elfies", json={"name": "空刺激测试"}).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"message": "", "mode": "mock"},
    )

    assert response.status_code == 422


def test_static_shell_has_three_columns_without_top_navigation(tmp_path):
    client = TestClient(create_app(str(tmp_path)))

    response = client.get("/")

    assert response.status_code == 200
    assert 'class="elfie-panel"' in response.text
    assert 'class="timeline-panel"' in response.text
    assert 'class="detail-panel is-closed"' in response.text
    assert "<nav" not in response.text
    assert client.get("/static/app.js").status_code == 200
    styles = client.get("/static/styles.css")
    assert styles.status_code == 200
    assert "color-scheme: light" in styles.text

    runtime = client.get("/api/runtime/status")
    assert runtime.status_code == 200
    assert runtime.json()["scope"] == "development"
    assert str(tmp_path) in runtime.json()["config_dir"]


def test_real_mode_reports_missing_development_credentials(tmp_path):
    runtime_dir = tmp_path / "runtime"
    store = RuntimeLabConfigStore(str(runtime_dir))
    store.configure_provider(
        "openai",
        api_base="https://example.invalid/v1",
        api_mode="chat_completions",
        model="example-model",
        model_key="remote_deep",
    )
    client = TestClient(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json={"name": "真实模型配置测试"}).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"message": "你好", "mode": "real"},
    )

    assert response.status_code == 200
    assert response.json()["result"]["success"] is False
    assert "尚未配置可用凭据" in response.json()["error"]
