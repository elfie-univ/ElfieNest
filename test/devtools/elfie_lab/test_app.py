from fastapi.testclient import TestClient

from ai_runtime import RuntimeAgent
from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.gateway.request import RuntimeResult
from devtools.elfie_lab.app import create_app
from devtools.runtime_lab import RuntimeLabConfigStore


def _write_foods(runtime_dir, *, focus_model="ollama/focus", standard_model="ollama/qwen3.5:0.8b"):
    FoodCatalogStore(runtime_dir / "foods.yaml", runtime_dir / "food_history").save(
        FoodCatalog(
            recipes={
                "coarse": FoodRecipe("coarse", "粗粮", "", ExecutionProfile("ollama/qwen3.5:0.8b")),
                "standard": FoodRecipe("standard", "标准粮", "", ExecutionProfile(standard_model)),
                "focus": FoodRecipe(
                    "focus",
                    "清醒粮",
                    "",
                    ExecutionProfile(focus_model),
                    technical_fallbacks=(ExecutionProfile("ollama/qwen3.5:0.8b"),),
                ),
            }
        )
    )


def test_app_create_elfie_and_chat(tmp_path):
    client = TestClient(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

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


def test_app_rejects_empty_stimulus(tmp_path):
    client = TestClient(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    created = client.post("/api/elfies", json={"name": "空刺激测试"}).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"message": "", "food_key": "mock"},
    )

    assert response.status_code == 422


def test_static_shell_has_three_columns_without_top_navigation(tmp_path):
    runtime_dir = tmp_path / "runtime"
    client = TestClient(create_app(str(tmp_path / "data"), str(runtime_dir)))

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


def test_app_rejects_unknown_species_and_saves_portrait(tmp_path):
    client = TestClient(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

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

def test_default_app_shares_runtime_but_keeps_elfie_data_isolated(
    tmp_path, monkeypatch
):
    shared_runtime = tmp_path / "shared-runtime"
    elfie_data = tmp_path / "elfie-data"
    monkeypatch.setenv("ELFIE_HOME", str(shared_runtime))
    monkeypatch.setattr(
        "devtools.elfie_lab.app.list_installed_ollama_models",
        lambda config: (),
    )
    _write_foods(shared_runtime)

    app = create_app(str(elfie_data))
    client = TestClient(app)

    assert app.state.storage.root == elfie_data
    assert app.state.runtime_store.root == shared_runtime
    assert app.state.food_store.path == shared_runtime / "foods.yaml"
    assert client.get("/api/runtime/status").json()["scope"] == "shared"
    assert client.get("/api/runtime/foods").json()["configuration_command"] == (
        ".venv/bin/python -m ai_runtime.lab"
    )


def test_food_api_reports_primary_and_fallback_readiness(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir, focus_model="openai/example-model")
    store = RuntimeLabConfigStore(str(runtime_dir))
    store.configure_provider(
        "openai",
        api_base="https://example.invalid/v1",
        api_mode="chat_completions",
        model="example-model",
        model_key="remote_deep",
    )
    monkeypatch.setattr(
        "devtools.elfie_lab.app.list_installed_ollama_models",
        lambda config: ("qwen3.5:0.8b",),
    )
    client = TestClient(create_app(str(tmp_path / "data"), str(runtime_dir)))
    response = client.get("/api/runtime/foods")

    assert response.status_code == 200
    payload = response.json()
    focus = next(item for item in payload["items"] if item["key"] == "focus")
    runtime_lab_command = f"ELFIE_HOME={runtime_dir} .venv/bin/python -m ai_runtime.lab"
    assert payload["configuration_command"] == runtime_lab_command
    assert focus["model"] == "openai/example-model"
    assert focus["primary_ready"] is False
    assert focus["fallback_ready"] is True
    assert focus["credential_ready"] is True
    assert runtime_lab_command in focus["setup_commands"]


def test_non_mock_turn_uses_selected_food_and_runtime_catalog(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir)
    captured = {}

    def fake_run_with_food(runtime, **kwargs):
        captured["food_key"] = kwargs["food_key"]
        captured["catalog_path"] = runtime.food_catalog_store.path
        return RuntimeResult(
            text="粮食调用成功。[ACTION]nod_head[/ACTION]",
            mode="local",
            model_key="ollama/test-food-model",
            decision={"food": {"requested": "standard", "actual": "standard"}},
            food_requested="standard",
            food_used="standard",
            execution_stage="primary",
            actual_model="ollama/test-food-model",
        )

    monkeypatch.setattr(RuntimeAgent, "run_with_food", fake_run_with_food)
    monkeypatch.setattr(
        "devtools.elfie_lab.app.list_installed_ollama_models",
        lambda config: ("qwen3.5:0.8b",),
    )
    client = TestClient(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json={"name": "粮食交互测试"}).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"message": "你好", "food_key": "standard"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["food_key"] == "standard"
    assert payload["model_call"]["food_used"] == "standard"
    assert payload["model_call"]["provider"] == "ollama"
    assert payload["model_call"]["model"] == "ollama/test-food-model"
    assert captured == {
        "food_key": "standard",
        "catalog_path": runtime_dir / "foods.yaml",
    }


def test_turn_rejects_legacy_mode_and_unknown_food(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "devtools.elfie_lab.app.list_installed_ollama_models",
        lambda config: (),
    )
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir)
    client = TestClient(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json={"name": "粮食协议测试"}).json()
    endpoint = f"/api/elfies/{created['elfie_id']}/turns"

    legacy = client.post(endpoint, json={"message": "你好", "mode": "real"})
    missing = client.post(endpoint, json={"message": "你好"})
    unknown = client.post(
        endpoint,
        json={"message": "你好", "food_key": "not-a-food"},
    )

    assert legacy.status_code == 422
    assert missing.status_code == 422
    assert unknown.status_code == 422
    assert "不存在粮食" in unknown.json()["detail"]


def test_foods_api_returns_food_list(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "devtools.elfie_lab.app.list_installed_ollama_models",
        lambda config: (),
    )
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir)
    client = TestClient(create_app(str(tmp_path / "data"), str(runtime_dir)))

    response = client.get("/api/runtime/foods")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 1
    mock_food = next(f for f in items if f["key"] == "mock")
    assert mock_food["display_name"] == "模拟粮"
    assert mock_food["credential_ready"] is True


def test_uninstalled_ollama_food_is_disabled_with_setup_command(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "devtools.elfie_lab.app.list_installed_ollama_models",
        lambda config: ("another-model:latest",),
    )
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir)
    client = TestClient(create_app(str(tmp_path / "data"), str(runtime_dir)))

    food_payload = client.get("/api/runtime/foods").json()
    foods = food_payload["items"]
    standard = next(item for item in foods if item["key"] == "standard")

    assert standard["ready_for_attempt"] is False
    assert standard["unavailable_reason"] == "本地模型 qwen3.5:0.8b 尚未安装"
    assert standard["setup_commands"] == ["ollama pull qwen3.5:0.8b"]
    assert food_payload["configuration_command"].endswith(
        ".venv/bin/python -m ai_runtime.lab"
    )

    created = client.post("/api/elfies", json={"name": "未就绪粮食测试"}).json()
    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"message": "你好", "food_key": "standard"},
    )
    assert response.status_code == 422
    assert "ollama pull qwen3.5:0.8b" in response.json()["detail"]
