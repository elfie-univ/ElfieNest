from ai_runtime import RuntimeAgent
from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodPackage,
    ModelAssignment,
)
from ai_runtime.gateway.request import RuntimeResult
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from app.infrastructure.persistence.store import init_db
from devtools.elfie_lab.app import create_app
from devtools.runtime_lab import RuntimeLabConfigStore


def elfie_payload(name):
    return {
        "name": name,
        "species_id": "fox",
        "age_years": 2,
        "description": "验证粮食选择",
        "personality_description": "稳定、好奇",
        "appearance_description": "浅色毛发",
    }


def _write_foods(
    runtime_dir,
    *,
    focus_model="ollama/focus",
    standard_model="ollama/qwen3.5:0.8b",
):
    runtime_dir.mkdir(parents=True, exist_ok=True)
    db_path = runtime_dir / "nest.db"
    init_db(str(db_path))
    repository = SQLiteFoodPackageRepository(db_path)
    for package in (
            FoodPackage(
                key="coarse",
                display_name="粗粮",
                primary=ModelAssignment("ollama/qwen3.5:0.8b"),
            ),
            FoodPackage(
                key="standard",
                display_name="标准粮",
                primary=ModelAssignment(standard_model),
            ),
            FoodPackage(
                key="focus",
                display_name="清醒粮",
                primary=ModelAssignment(focus_model),
                fallback=ModelAssignment("ollama/qwen3.5:0.8b"),
            ),
    ):
        repository.create(package)


def test_default_app_uses_developer_runtime_and_keeps_production_isolated(
    tmp_path, monkeypatch, client_for
):
    production_home = tmp_path / "production"
    developer_home = tmp_path / "developer"
    developer_runtime = developer_home / "runtime_lab"
    elfie_data = tmp_path / "elfie-data"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))
    monkeypatch.setenv("ELFIE_DEV_HOME", str(developer_home))
    monkeypatch.setattr(
        "devtools.elfie_lab.food_status.list_installed_ollama_models",
        lambda config: (),
    )
    _write_foods(developer_runtime)

    app = create_app(str(elfie_data))
    client = client_for(app)

    assert app.state.storage.root == elfie_data
    assert app.state.runtime_store.root == developer_runtime
    assert (developer_runtime / "nest.db").exists()
    assert not (developer_runtime / "foods.yaml").exists()
    assert client.get("/api/runtime/status").json()["scope"] == "developer"
    assert not production_home.exists()
    assert client.get("/api/runtime/foods").json()["configuration_command"] == (
        f"ELFIE_HOME={developer_runtime} .venv/bin/python -m ai_runtime.lab"
    )


def test_food_api_reports_primary_and_fallback_readiness(
    tmp_path, monkeypatch, client_for
):
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
        "devtools.elfie_lab.food_status.list_installed_ollama_models",
        lambda config: ("qwen3.5:0.8b",),
    )
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
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


def test_non_mock_turn_uses_selected_food_and_runtime_catalog(
    tmp_path, monkeypatch, client_for
):
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir)
    captured = {}

    def fake_run_with_food(runtime, **kwargs):
        captured["food_key"] = kwargs["food_key"]
        captured["catalog_path"] = runtime.food_catalog_repository._db_path
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
        "devtools.elfie_lab.food_status.list_installed_ollama_models",
        lambda config: ("qwen3.5:0.8b",),
    )
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json=elfie_payload("粮食交互测试")).json()

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
        "catalog_path": str(runtime_dir / "nest.db"),
    }


def test_turn_rejects_legacy_mode_and_unknown_food(tmp_path, monkeypatch, client_for):
    monkeypatch.setattr(
        "devtools.elfie_lab.food_status.list_installed_ollama_models",
        lambda config: (),
    )
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json=elfie_payload("粮食协议测试")).json()
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


def test_foods_api_returns_food_list(tmp_path, monkeypatch, client_for):
    monkeypatch.setattr(
        "devtools.elfie_lab.food_status.list_installed_ollama_models",
        lambda config: (),
    )
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    response = client.get("/api/runtime/foods")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["key"] for item in items] == [
        FOOD_EMERGENCY_ID,
        FOOD_COMMON_ID,
        "coarse",
        "focus",
        "standard",
    ]
    assert all(item["credential_ready"] is False for item in items)


def test_default_elfie_lab_shows_unconfigured_foods_as_disabled_when_catalog_is_absent(
    tmp_path, monkeypatch, client_for
):
    # Given
    monkeypatch.setattr(
        "devtools.elfie_lab.food_status.list_installed_ollama_models",
        lambda config: (),
    )
    runtime_dir = tmp_path / "empty-runtime"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    # When
    response = client.get("/api/runtime/foods")

    # Then
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["key"] for item in items] == [FOOD_EMERGENCY_ID, FOOD_COMMON_ID]
    assert all(not item["ready_for_attempt"] for item in items)


def test_uninstalled_ollama_food_is_disabled_with_setup_command(
    tmp_path, monkeypatch, client_for
):
    monkeypatch.setattr(
        "devtools.elfie_lab.food_status.list_installed_ollama_models",
        lambda config: ("another-model:latest",),
    )
    runtime_dir = tmp_path / "runtime"
    _write_foods(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    food_payload = client.get("/api/runtime/foods").json()
    foods = food_payload["items"]
    standard = next(item for item in foods if item["key"] == "standard")

    assert standard["ready_for_attempt"] is False
    assert standard["unavailable_reason"] == "本地模型 qwen3.5:0.8b 尚未安装"
    assert standard["setup_commands"] == ["ollama pull qwen3.5:0.8b"]
    assert food_payload["configuration_command"].endswith(
        ".venv/bin/python -m ai_runtime.lab"
    )

    created = client.post("/api/elfies", json=elfie_payload("未就绪粮食测试")).json()
    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"message": "你好", "food_key": "standard"},
    )
    assert response.status_code == 422
    assert "ollama pull qwen3.5:0.8b" in response.json()["detail"]
