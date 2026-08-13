from pathlib import Path

import pytest

from devtools.elfie_lab.app import create_app
from devtools.elfie_lab.model_execution_foods import ElfieLabModelEnvironment
from devtools.elfie_lab.storage import ElfieLabStorage
from elfie.brain.reasoning.food_port import FOOD_COMMON_ID, FOOD_EMERGENCY_ID
from infrastructure.models.model_execution_agent import ModelExecutionAgent
from infrastructure.models.model_execution_contracts import (
    StructuredGenerationMode,
    StructuredModelExecutionCapabilities,
    StructuredModelExecutionResult,
)
from infrastructure.persistence.food import SQLiteFoodAdapter


@pytest.fixture(autouse=True)
def skip_frontend_bundle(monkeypatch):
    monkeypatch.setattr(
        "devtools.elfie_lab.app.mount_static_surfaces",
        lambda _app: None,
    )


def elfie_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "species_id": "fox",
        "age_years": 2,
        "description": "验证粮食选择",
        "personality_description": "稳定、好奇",
        "appearance_description": "浅色毛发",
    }


def _configure_local(runtime_dir: Path, model: str = "qwen3.5:0.8b") -> None:
    ElfieLabModelEnvironment(runtime_dir).configure(mode="local", model=model)


def test_default_app_uses_elfie_lab_root_and_keeps_production_isolated(
    tmp_path, monkeypatch, client_for
):
    production_home = tmp_path / "production"
    developer_home = tmp_path / "developer"
    elfie_data = tmp_path / "elfie-data"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))
    monkeypatch.setenv("ELFIE_DEV_HOME", str(developer_home))
    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.OllamaManager.list_installed_models",
        lambda _manager: (),
    )

    app = create_app(str(elfie_data))
    client = client_for(app)

    expected_root = elfie_data / "runtime"
    assert app.state.storage.root == elfie_data
    assert app.state.model_execution.root == expected_root.resolve()
    assert (expected_root / "nest.db").exists()
    assert client.get("/api/runtime/status").json()["scope"] == "override"
    payload = client.get("/api/runtime/foods").json()
    assert payload["local_models"] == []
    assert "configuration_command" not in payload
    assert not production_home.exists()


def test_app_accepts_existing_lab_storage_with_independent_runtime_root(
    tmp_path, monkeypatch, client_for
):
    developer_home = tmp_path / "developer"
    lab_root = developer_home / "elfie_lab"
    monkeypatch.setenv("ELFIE_DEV_HOME", str(developer_home))
    ElfieLabStorage(lab_root)
    assert (lab_root / "sessions").is_dir()
    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.OllamaManager.list_installed_models",
        lambda _manager: (),
    )

    app = create_app(str(lab_root))
    client = client_for(app)

    assert client.get("/api/health").json()["status"] == "ok"
    assert app.state.storage.root == lab_root
    assert app.state.model_execution.root == (lab_root / "runtime").resolve()
    assert (lab_root / "runtime" / "nest.db").is_file()


def test_configure_local_model_creates_one_test_food(tmp_path, monkeypatch, client_for):
    runtime_dir = tmp_path / "elfie-lab"
    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.OllamaManager.list_installed_models",
        lambda _manager: ("qwen3.5:0.8b",),
    )
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    response = client.post(
        "/api/runtime/foods/configure",
        json={"mode": "local", "model": "qwen3.5:0.8b"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_food"] == "elfie_lab_test"
    food = next(item for item in payload["items"] if item["key"] == "elfie_lab_test")
    assert food["ready_for_attempt"] is True
    assert food["model"].endswith("/qwen3.5:0.8b")
    assert payload["local_models"] == ["qwen3.5:0.8b"]


def test_configure_openai_compatible_saves_secret_without_preflight(
    tmp_path, monkeypatch, client_for
):
    runtime_dir = tmp_path / "elfie-lab"
    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.OllamaManager.list_installed_models",
        lambda _manager: (),
    )
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    response = client.post(
        "/api/runtime/foods/configure",
        json={
            "mode": "openai",
            "api_base": "https://example.invalid/v1",
            "api_key": "test-token-not-for-response",
            "model": "example-model",
        },
    )

    assert response.status_code == 200
    assert "test-token-not-for-response" not in response.text
    item = next(
        item for item in response.json()["items"] if item["key"] == "elfie_lab_test"
    )
    assert item["ready_for_attempt"] is True
    runtime = ElfieLabModelEnvironment(runtime_dir)
    config = runtime.load_model_execution_config()
    connection = next(
        value
        for key, value in config.providers.items()
        if key.startswith("custom_openai_")
    )
    assert connection["api_base"] == "https://example.invalid/v1"
    assert connection["api_key"] == "test-token-not-for-response"


def test_configure_replaces_the_previous_test_food(tmp_path, client_for, monkeypatch):
    runtime_dir = tmp_path / "elfie-lab"
    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.OllamaManager.list_installed_models",
        lambda _manager: (),
    )
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    first = client.post(
        "/api/runtime/foods/configure",
        json={"mode": "local", "model": "first-model"},
    )
    second = client.post(
        "/api/runtime/foods/configure",
        json={"mode": "local", "model": "second-model"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    packages = SQLiteFoodAdapter(runtime_dir / "nest.db").list_packages()
    selected = next(item for item in packages if item.food_id == "elfie_lab_test")
    assert selected.primary_model.endswith("/second-model")
    assert len([item for item in packages if item.food_id == "elfie_lab_test"]) == 1


def test_non_mock_turn_uses_selected_food_and_runtime_catalog(
    tmp_path, monkeypatch, client_for
):
    runtime_dir = tmp_path / "elfie-lab"
    _configure_local(runtime_dir)
    captured = {}

    def fake_structured_capabilities(runtime, food_key=None, food_unavailable=False):
        captured["food_key"] = food_key
        assert food_unavailable is False
        captured["catalog_path"] = runtime.food_catalog_repository._db_path
        return StructuredModelExecutionCapabilities(
            provider="ollama",
            model_key="ollama/test-food-model",
            supports_json_schema=False,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def fake_generate_structured(runtime, request):
        assert request.food_key == "elfie_lab_test"
        return StructuredModelExecutionResult(
            text="粮食调用成功。[ACTION]nod_head[/ACTION]",
            selected_mode=StructuredGenerationMode.JSON_TEXT,
            provider="ollama",
            model_key="ollama/test-food-model",
        )

    monkeypatch.setattr(
        ModelExecutionAgent, "structured_capabilities", fake_structured_capabilities
    )
    monkeypatch.setattr(ModelExecutionAgent, "generate_structured", fake_generate_structured)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json=elfie_payload("粮食交互测试")).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={
            "source_domain": "communication",
            "message": "你好",
            "food_key": "elfie_lab_test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["food_key"] == "elfie_lab_test"
    assert payload["model_call"]["food_used"] == "elfie_lab_test"
    assert captured == {
        "food_key": "elfie_lab_test",
        "catalog_path": str(runtime_dir / "nest.db"),
    }


def test_turn_rejects_legacy_mode_and_unknown_food(tmp_path, client_for):
    runtime_dir = tmp_path / "elfie-lab"
    _configure_local(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json=elfie_payload("粮食协议测试")).json()
    endpoint = f"/api/elfies/{created['elfie_id']}/turns"

    legacy = client.post(endpoint, json={"message": "你好", "mode": "real"})
    unknown = client.post(
        endpoint,
        json={
            "source_domain": "communication",
            "message": "你好",
            "food_key": "not-a-food",
        },
    )

    assert legacy.status_code == 422
    assert unknown.status_code == 422
    assert "不存在粮食" in unknown.json()["detail"]


def test_empty_catalog_exposes_only_unconfigured_system_foods(tmp_path, client_for):
    runtime_dir = tmp_path / "empty-elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    response = client.get("/api/runtime/foods")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["key"] for item in items] == [FOOD_EMERGENCY_ID, FOOD_COMMON_ID]
    assert all(not item["ready_for_attempt"] for item in items)
