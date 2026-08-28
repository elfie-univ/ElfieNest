from typing import Any

import pytest

from app.features.configuration.food import StoredFoodPackage
from devtools.elfie_lab.app import create_app
from devtools.elfie_lab.model_execution_foods import (
    ElfieLabModelEnvironment,
    validate_food_connection,
)
from devtools.elfie_lab.storage import ElfieLabStorage
from elfie.brain.reasoning.food_port import FOOD_COMMON_ID
from infrastructure.models.model_execution_agent import ModelExecutionAgent
from infrastructure.models.model_execution_contracts import (
    StructuredGenerationMode,
    StructuredModelExecutionCapabilities,
    StructuredModelExecutionResult,
)
from infrastructure.models.ollama.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaPlatformAdapter,
    OllamaProbe,
)
from infrastructure.models.provider_records import ProviderModelRecord
from infrastructure.persistence.configuration.secrets import read_secrets
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.provider_connections import ProviderConnectionStore


@pytest.fixture(autouse=True)
def skip_frontend_bundle(monkeypatch):
    monkeypatch.setattr(
        "devtools.elfie_lab.app.mount_static_surfaces",
        lambda _app: None,
    )


@pytest.fixture(autouse=True)
def successful_food_connection_probe(monkeypatch):
    calls: list[dict[str, str]] = []

    def probe(
        *, api_mode: str, api_base: str, api_key: str, primary_model: str
    ) -> None:
        calls.append(
            {
                "api_mode": api_mode,
                "api_base": api_base,
                "api_key": api_key,
                "primary_model": primary_model,
            }
        )

    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.validate_food_connection",
        probe,
        raising=False,
    )
    return calls


def elfie_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "species_id": "fox",
        "age_years": 2,
        "description": "验证粮食选择",
        "personality_description": "稳定、好奇",
        "appearance_description": "浅色毛发",
    }


def food_payload(**overrides: Any) -> dict[str, object]:
    payload: dict[str, object] = {
        "connection_type": "openai",
        "display_name": "火山测试粮",
        "api_base": "https://example.invalid/v1/",
        "api_key": "test-token-not-for-response",
        "models": [
            "main-model",
            "reasoning-model",
            "vision-model",
            "tool-model",
            "fallback-model",
        ],
        "primary_model": "main-model",
        "reasoning_model": "reasoning-model",
        "vision_model": "vision-model",
        "tool_model": "tool-model",
        "fallback_model": "fallback-model",
    }
    payload.update(overrides)
    return payload


def configure_food(client, **overrides: Any):
    return client.post(
        "/api/runtime/foods/configure",
        json=food_payload(**overrides),
    )


def detail_text(response) -> str:
    detail = response.json().get("detail", "")
    if isinstance(detail, list):
        return " ".join(str(item.get("msg", "")) for item in detail)
    return str(detail)


def test_default_app_uses_elfie_lab_root_and_keeps_production_isolated(
    tmp_path, monkeypatch, client_for
):
    production_home = tmp_path / "production"
    developer_home = tmp_path / "developer"
    elfie_data = tmp_path / "elfie-data"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))
    monkeypatch.setenv("ELFIE_DEV_HOME", str(developer_home))

    app = create_app(str(elfie_data))
    client = client_for(app)

    expected_root = elfie_data / "runtime"
    assert app.state.storage.root == elfie_data
    assert app.state.model_execution.root == expected_root.resolve()
    assert (expected_root / "nest.db").exists()
    assert client.get("/api/runtime/status").json()["scope"] == "override"
    payload = client.get("/api/runtime/foods").json()
    assert payload == {"items": []}
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

    app = create_app(str(lab_root))
    client = client_for(app)

    assert client.get("/api/health").json()["status"] == "ok"
    assert app.state.storage.root == lab_root
    assert app.state.model_execution.root == (lab_root / "runtime").resolve()
    assert (lab_root / "runtime" / "nest.db").is_file()


def test_create_food_validates_and_persists_one_openai_subscription(
    tmp_path, client_for, successful_food_connection_probe
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    response = configure_food(client)

    assert response.status_code == 200
    assert "test-token-not-for-response" not in response.text
    assert successful_food_connection_probe == [
        {
            "api_mode": "chat_completions",
            "api_base": "https://example.invalid/v1",
            "api_key": "test-token-not-for-response",
            "primary_model": "main-model",
        }
    ]
    payload = response.json()
    selected_food = payload["selected_food"]
    assert selected_food.startswith("elfie_lab_food_")
    assert payload["items"] == [
        {
            "key": selected_food,
            "subscription_id": "custom_openai_0001",
            "subscription_name": "火山测试粮",
            "display_name": "火山测试粮",
            "description": "已配置，可用于真实对话",
            "model": "custom_openai_0001/main-model",
            "reasoning": "on",
            "ready_for_attempt": True,
            "unavailable_reason": "",
            "connection_type": "openai",
            "api_base": "https://example.invalid/v1",
            "models": [
                "main-model",
                "reasoning-model",
                "vision-model",
                "tool-model",
                "fallback-model",
            ],
            "primary_model": "main-model",
            "reasoning_model": "reasoning-model",
            "vision_model": "vision-model",
            "tool_model": "tool-model",
            "fallback_model": "fallback-model",
        }
    ]

    runtime = ElfieLabModelEnvironment(runtime_dir)
    provider = runtime.load_model_execution_config().providers["custom_openai_0001"]
    assert provider["api_base"] == "https://example.invalid/v1"
    assert provider["api_key"] == "test-token-not-for-response"
    package = SQLiteFoodAdapter(runtime_dir / "nest.db").get_package(selected_food)
    assert package is not None
    assert package.primary_model == "custom_openai_0001/main-model"


def test_create_food_reuses_existing_shared_subscription_without_duplicate_provider(
    tmp_path, client_for, successful_food_connection_probe
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    first = configure_food(client)
    assert first.status_code == 200, first.text
    first_food = first.json()["items"][0]

    second = configure_food(
        client,
        subscription_id=first_food["subscription_id"],
        subscription_name=None,
        display_name="复用同一订阅的粮食",
        api_base=None,
        api_key=None,
        primary_model="reasoning-model",
        reasoning_model="main-model",
        vision_model="",
        tool_model="",
        fallback_model="",
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == 2
    assert {item["subscription_id"] for item in second.json()["items"]} == {
        first_food["subscription_id"]
    }
    connections = (
        ProviderConnectionStore(runtime_dir / "configs" / "providers.yaml")
        .load()
        .connections
    )
    assert list(connections) == [first_food["subscription_id"]]
    assert successful_food_connection_probe[-1]["primary_model"] == "reasoning-model"


def test_reviewer_subscriptions_share_provider_records_without_creating_food(
    tmp_path, client_for, monkeypatch
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    monkeypatch.setattr(
        "devtools.elfie_lab.reviewer_subscriptions.validate_reviewer_connection",
        lambda **_: None,
    )
    created = client.post(
        "/api/runtime/reviewer-subscriptions",
        json={
            "display_name": "独立评审订阅",
            "api_base": "https://judge.example.invalid/v1",
            "api_key": "test-reviewer-key",
            "models": ["judge-main", "judge-vision"],
        },
    )
    assert created.status_code == 200, created.text
    item = created.json()["item"]
    assert item["display_name"] == "独立评审订阅"
    assert item["models"] == ["judge-main", "judge-vision"]
    assert item["has_api_key"] is True
    assert "test-reviewer-key" not in created.text
    assert client.get("/api/runtime/foods").json()["items"] == []
    runtime = ElfieLabModelEnvironment(runtime_dir)
    assert item["id"] in runtime.load_model_execution_config().providers
    assert all(
        not reference.startswith(f"{item['id']}/")
        for reference in runtime.model_evidence()
    ), "评审订阅必须仍然不进入候选粮食的模型证据"
    subscriptions = client.get("/api/runtime/model-subscriptions")
    assert subscriptions.status_code == 200
    shared = next(
        entry for entry in subscriptions.json()["items"] if entry["id"] == item["id"]
    )
    assert shared["supports_food"] is True
    assert shared["supports_reviewer"] is True


def test_reviewer_subscription_rejects_local_or_non_https_endpoint(
    tmp_path, client_for, monkeypatch
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    monkeypatch.setattr(
        "devtools.elfie_lab.reviewer_subscriptions.validate_reviewer_connection",
        lambda **_: (_ for _ in ()).throw(AssertionError("本地地址不应发起请求")),
    )
    for api_base in (
        "http://judge.example.invalid/v1",
        "https://127.0.0.1/v1",
        "https://localhost/v1",
    ):
        response = client.post(
            "/api/runtime/reviewer-subscriptions",
            json={
                "display_name": "不允许的评审订阅",
                "api_base": api_base,
                "api_key": "key",
                "models": ["judge-main"],
            },
        )
        assert response.status_code == 422
        assert (
            "远程" in response.json()["detail"] or "本机" in response.json()["detail"]
        )


def test_local_food_subscription_is_not_a_reviewer_option(
    tmp_path, client_for, successful_food_connection_probe
):
    """A shared Provider record remains Food-only when its endpoint is local."""
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    created = configure_food(
        client,
        display_name="仅用于粮食的本地订阅",
        api_base="http://127.0.0.1:11434/v1",
        api_key="",
        models=["local-main"],
        primary_model="local-main",
        reasoning_model="",
        vision_model="",
        tool_model="",
        fallback_model="",
    )
    assert created.status_code == 200, created.text

    food = created.json()["items"][0]
    reviewer_options = client.get("/api/runtime/reviewer-subscriptions")
    assert reviewer_options.status_code == 200
    assert reviewer_options.json() == {"items": []}

    shared_options = client.get("/api/runtime/model-subscriptions")
    assert shared_options.status_code == 200
    local = next(
        item
        for item in shared_options.json()["items"]
        if item["id"] == food["subscription_id"]
    )
    assert local["supports_food"] is True
    assert local["supports_reviewer"] is False


def test_create_and_edit_custom_food_without_api_key(
    tmp_path, client_for, successful_food_connection_probe
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    created = configure_food(
        client,
        display_name="本地免鉴权粮",
        api_base="http://127.0.0.1:11434/v1",
        api_key="",
        models=["local-main", "local-vision"],
        primary_model="local-main",
        reasoning_model="",
        vision_model="local-vision",
        tool_model="",
        fallback_model="",
    )

    assert created.status_code == 200
    food_id = created.json()["selected_food"]
    assert successful_food_connection_probe[-1] == {
        "api_mode": "chat_completions",
        "api_base": "http://127.0.0.1:11434/v1",
        "api_key": "",
        "primary_model": "local-main",
    }

    runtime = ElfieLabModelEnvironment(runtime_dir)
    connection = (
        ProviderConnectionStore(runtime.providers_path)
        .load()
        .connections["custom_openai_0001"]
    )
    assert connection.auth_type == "none"
    assert connection.credential_ref == ""
    assert read_secrets(runtime.env_path) == {}
    provider = runtime.load_model_execution_config().providers["custom_openai_0001"]
    assert provider.get("api_key", "") == ""
    assert provider["status"] == "active"

    edited = client.post(
        "/api/runtime/foods/configure",
        json={
            "food_id": food_id,
            "connection_type": "openai",
            "display_name": "本地免鉴权粮（已编辑）",
            "models": ["local-main"],
            "primary_model": "local-main",
        },
    )

    assert edited.status_code == 200
    assert successful_food_connection_probe[-1] == {
        "api_mode": "chat_completions",
        "api_base": "http://127.0.0.1:11434/v1",
        "api_key": "",
        "primary_model": "local-main",
    }
    assert edited.json()["items"][0]["display_name"] == "本地免鉴权粮（已编辑）"
    assert read_secrets(runtime.env_path) == {}


def test_probe_local_ollama_uses_default_loopback_endpoint(
    tmp_path, client_for, monkeypatch
):
    observed = []

    def probe(_adapter, binding):
        observed.append(binding)
        return OllamaProbe(
            state="healthy",
            endpoint=binding.api_base,
            version="0.11.4",
        )

    monkeypatch.setattr(OllamaPlatformAdapter, "probe", probe)
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "elfie-lab")))

    response = client.post("/api/runtime/ollama/probe", json={})

    assert response.status_code == 200
    assert response.json() == {
        "state": "healthy",
        "endpoint": DEFAULT_OLLAMA_ENDPOINT,
        "version": "0.11.4",
        "message": "已连接本机 Ollama",
    }
    assert len(observed) == 1
    assert observed[0].api_base == DEFAULT_OLLAMA_ENDPOINT

    unsafe = client.post(
        "/api/runtime/ollama/probe",
        json={"api_base": "https://remote.example/v1"},
    )
    assert unsafe.status_code == 422
    assert "本机回环地址" in detail_text(unsafe)


def test_local_food_validation_uses_native_ollama_api(monkeypatch):
    observed = {}

    def call_ollama(
        api_base,
        model,
        messages,
        temperature,
        max_tokens,
        **options,
    ):
        observed.update(
            {
                "api_base": api_base,
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout_seconds": options["timeout_seconds"],
            }
        )
        return "OK", {}

    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.call_ollama_api",
        call_ollama,
    )
    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.call_openai_compatible_api",
        lambda *_args, **_kwargs: pytest.fail("本机 Ollama 不应走 OpenAI 兼容路径"),
    )

    validate_food_connection(
        api_mode="ollama",
        api_base=DEFAULT_OLLAMA_ENDPOINT,
        api_key="",
        primary_model="gemma3:270m",
    )

    assert observed == {
        "api_base": DEFAULT_OLLAMA_ENDPOINT,
        "model": "gemma3:270m",
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "temperature": 0.0,
        "max_tokens": 8,
        "timeout_seconds": 20.0,
    }


def test_create_and_edit_local_ollama_food_without_api_key(
    tmp_path, client_for, successful_food_connection_probe
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    created = configure_food(
        client,
        connection_type="ollama",
        display_name="本机 Ollama 粮",
        api_base="",
        api_key="",
        models=["gemma3:270m", "qwen3:4b"],
        primary_model="gemma3:270m",
        reasoning_model="qwen3:4b",
        vision_model="",
        tool_model="",
        fallback_model="",
    )

    assert created.status_code == 200
    food_id = created.json()["selected_food"]
    assert successful_food_connection_probe[-1] == {
        "api_mode": "ollama",
        "api_base": DEFAULT_OLLAMA_ENDPOINT,
        "api_key": "",
        "primary_model": "gemma3:270m",
    }
    item = created.json()["items"][0]
    assert item["connection_type"] == "ollama"
    assert item["api_base"] == DEFAULT_OLLAMA_ENDPOINT
    assert item["model"] == "ollama_0001/gemma3:270m"

    runtime = ElfieLabModelEnvironment(runtime_dir)
    connection = (
        ProviderConnectionStore(runtime.providers_path)
        .load()
        .connections["ollama_0001"]
    )
    assert connection.catalog_id == "ollama"
    assert connection.api_mode == "ollama"
    assert connection.auth_type == "none"
    assert connection.credential_ref == ""
    assert read_secrets(runtime.env_path) == {}

    edited = client.post(
        "/api/runtime/foods/configure",
        json={
            "food_id": food_id,
            "connection_type": "ollama",
            "display_name": "本机 Ollama 粮（已编辑）",
            "models": ["gemma3:270m"],
            "primary_model": "gemma3:270m",
        },
    )

    assert edited.status_code == 200
    assert successful_food_connection_probe[-1]["api_mode"] == "ollama"
    assert edited.json()["items"][0]["display_name"] == "本机 Ollama 粮（已编辑）"


def test_existing_ollama_food_without_saved_url_uses_the_default_endpoint(
    tmp_path, client_for, successful_food_connection_probe
):
    runtime_dir = tmp_path / "elfie-lab"
    runtime = ElfieLabModelEnvironment(runtime_dir)
    ProviderConnectionStore(runtime.providers_path).create(
        catalog_id="ollama",
        alias="旧本机粮",
        api_mode="ollama",
        auth_type="none",
        models=(
            ProviderModelRecord(
                endpoint_model_id="legacy-model",
                display_name="legacy-model",
                source="manual",
            ),
        ),
    )
    runtime.food_store().create_package(
        StoredFoodPackage(
            food_id="legacy-ollama-food",
            display_name="旧本机粮",
            primary_model="ollama_0001/legacy-model",
            enabled=True,
            archived=False,
        )
    )
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    item = client.get("/api/runtime/foods").json()["items"][0]
    assert item["connection_type"] == "ollama"
    assert item["api_base"] == DEFAULT_OLLAMA_ENDPOINT

    edited = client.post(
        "/api/runtime/foods/configure",
        json={
            "food_id": "legacy-ollama-food",
            "connection_type": "ollama",
            "display_name": "旧本机粮（已编辑）",
            "models": ["legacy-model"],
            "primary_model": "legacy-model",
        },
    )

    assert edited.status_code == 200
    assert successful_food_connection_probe[-1]["api_base"] == DEFAULT_OLLAMA_ENDPOINT


def test_failed_connection_validation_does_not_save_food_or_credentials(
    tmp_path, client_for, monkeypatch
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    def fail_probe(**_kwargs: str) -> None:
        raise ValueError("模型连接验证失败：API Key 无效")

    monkeypatch.setattr(
        "devtools.elfie_lab.model_execution_foods.validate_food_connection",
        fail_probe,
        raising=False,
    )

    response = configure_food(client)

    assert response.status_code == 422
    assert "API Key 无效" in detail_text(response)
    assert client.get("/api/runtime/foods").json() == {"items": []}
    runtime = ElfieLabModelEnvironment(runtime_dir)
    assert ProviderConnectionStore(runtime.providers_path).load().connections == {}
    assert read_secrets(runtime.env_path) == {}


def test_edit_food_keeps_subscription_credentials_and_updates_models(
    tmp_path, client_for, successful_food_connection_probe
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = configure_food(client)
    food_id = created.json()["selected_food"]

    response = client.post(
        "/api/runtime/foods/configure",
        json={
            "food_id": food_id,
            "connection_type": "openai",
            "display_name": "更新后的粮食",
            "models": ["second-model", "second-vision"],
            "primary_model": "second-model",
            "reasoning_model": "",
            "vision_model": "second-vision",
            "tool_model": "",
            "fallback_model": "",
        },
    )

    assert response.status_code == 200
    assert successful_food_connection_probe[-1] == {
        "api_mode": "chat_completions",
        "api_base": "https://example.invalid/v1",
        "api_key": "test-token-not-for-response",
        "primary_model": "second-model",
    }
    assert len(successful_food_connection_probe) == 2
    item = response.json()["items"][0]
    assert item["key"] == food_id
    assert item["display_name"] == "更新后的粮食"
    assert item["models"] == ["second-model", "second-vision"]
    assert item["primary_model"] == "second-model"
    assert item["reasoning_model"] == ""
    assert item["vision_model"] == "second-vision"

    runtime = ElfieLabModelEnvironment(runtime_dir)
    document = ProviderConnectionStore(runtime.providers_path).load()
    assert tuple(document.connections) == ("custom_openai_0001",)
    connection = document.connections["custom_openai_0001"]
    assert connection.api_base == "https://example.invalid/v1"
    assert [model.endpoint_model_id for model in connection.models] == [
        "second-model",
        "second-vision",
    ]
    assert runtime.resolve_secret(connection.credential_ref) == (
        "test-token-not-for-response"
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"api_base": ""}, "新建粮食必须填写 API URL"),
        (
            {"connection_type": "ollama", "api_base": "", "api_key": "secret"},
            "本机 Ollama 不需要 API Key",
        ),
        (
            {
                "connection_type": "ollama",
                "api_base": "https://remote.example/v1",
                "api_key": "",
            },
            "本机回环地址",
        ),
        ({"models": []}, "粮食配置至少要包含一个模型"),
        ({"primary_model": "unknown"}, "主模型必须来自“模型列表”"),
        ({"reasoning_model": "unknown"}, "reasoning_model必须来自“模型列表”"),
    ],
)
def test_food_configuration_rejects_invalid_inputs(
    tmp_path, client_for, overrides, expected
):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "elfie-lab")))

    response = configure_food(client, **overrides)

    assert response.status_code == 422
    assert expected in detail_text(response)


def test_edit_rejects_credentials_and_unknown_food_id(tmp_path, client_for):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    food_id = configure_food(client).json()["selected_food"]
    edit_payload = {
        "food_id": food_id,
        "connection_type": "openai",
        "display_name": "不能改订阅",
        "models": ["main-model"],
        "primary_model": "main-model",
    }

    changed_url = client.post(
        "/api/runtime/foods/configure",
        json={**edit_payload, "api_base": "https://changed.invalid/v1"},
    )
    changed_key = client.post(
        "/api/runtime/foods/configure",
        json={**edit_payload, "api_key": "changed-key"},
    )
    unknown = client.post(
        "/api/runtime/foods/configure",
        json={**edit_payload, "food_id": "missing-food"},
    )
    changed_connection_type = client.post(
        "/api/runtime/foods/configure",
        json={**edit_payload, "connection_type": "ollama"},
    )

    assert changed_url.status_code == 422
    assert "不能修改 API URL" in detail_text(changed_url)
    assert changed_key.status_code == 422
    assert "不能修改 API Key" in detail_text(changed_key)
    assert unknown.status_code == 422
    assert "不存在该粮食" in detail_text(unknown)
    assert changed_connection_type.status_code == 422
    assert "不能修改连接方式" in detail_text(changed_connection_type)


def test_delete_food_keeps_shared_subscription_and_secret(tmp_path, client_for):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    food_id = configure_food(client).json()["selected_food"]
    runtime = ElfieLabModelEnvironment(runtime_dir)
    assert read_secrets(runtime.env_path)

    response = client.delete(f"/api/runtime/foods/{food_id}")

    assert response.status_code == 200
    assert response.json() == {"deleted_food": food_id}
    assert client.get("/api/runtime/foods").json() == {"items": []}
    connections = ProviderConnectionStore(runtime.providers_path).load().connections
    assert set(connections) == {"custom_openai_0001"}
    assert read_secrets(runtime.env_path)


def test_delete_rejects_unknown_and_system_food(tmp_path, client_for):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    unknown = client.delete("/api/runtime/foods/missing-food")
    system = client.delete(f"/api/runtime/foods/{FOOD_COMMON_ID}")

    assert unknown.status_code == 422
    assert "不存在该粮食" in detail_text(unknown)
    assert system.status_code == 422
    assert "系统粮食" in detail_text(system)


def test_non_mock_turn_uses_selected_food_and_runtime_catalog(
    tmp_path, monkeypatch, client_for
):
    runtime_dir = tmp_path / "elfie-lab"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    food_id = configure_food(client).json()["selected_food"]
    captured = {}

    def fake_structured_capabilities(runtime, food_key=None, food_unavailable=False):
        captured["food_key"] = food_key
        assert food_unavailable is False
        captured["catalog_path"] = runtime.food_catalog_repository._db_path
        return StructuredModelExecutionCapabilities(
            provider="custom_openai",
            model_key="custom_openai/test-food-model",
            supports_json_schema=False,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def fake_generate_structured(runtime, request):
        assert request.food_key == food_id
        return StructuredModelExecutionResult(
            text="粮食调用成功。[ACTION]nod_head[/ACTION]",
            selected_mode=StructuredGenerationMode.JSON_TEXT,
            provider="custom_openai",
            model_key="custom_openai/test-food-model",
        )

    monkeypatch.setattr(
        ModelExecutionAgent, "structured_capabilities", fake_structured_capabilities
    )
    monkeypatch.setattr(
        ModelExecutionAgent, "generate_structured", fake_generate_structured
    )
    created = client.post("/api/elfies", json=elfie_payload("粮食交互测试")).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={
            "source_domain": "communication",
            "message": "你好",
            "food_key": food_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["food_key"] == food_id
    assert payload["model_call"]["food_used"] == food_id
    assert captured == {
        "food_key": food_id,
        "catalog_path": str(runtime_dir / "nest.db"),
    }


def test_turn_rejects_legacy_mode_and_unknown_food(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "elfie-lab")))
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
    assert "不存在粮食" in detail_text(unknown)


def test_empty_catalog_hides_internal_system_foods(tmp_path, client_for):
    client = client_for(
        create_app(str(tmp_path / "data"), str(tmp_path / "empty-elfie-lab"))
    )

    response = client.get("/api/runtime/foods")

    assert response.status_code == 200
    assert response.json() == {"items": []}
