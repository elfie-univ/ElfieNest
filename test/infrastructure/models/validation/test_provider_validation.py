import json
import urllib.error

from infrastructure.models.validation.provider_validation import (
    ProviderValidationRunner,
    classify_latency,
    discover_provider_models,
    discover_provider_models_result,
)
from infrastructure.models.validation.validation_models import CheckStatus
from test.support.model_execution import model_execution_config


def test_latency_is_classified_for_reports():
    assert classify_latency(500) == "fast"
    assert classify_latency(2_000) == "normal"
    assert classify_latency(8_000) == "slow"


def test_transport_probe_uses_get_only_and_treats_missing_models_endpoint_as_reachable(
    monkeypatch, tmp_path
):
    from infrastructure.models.catalog import verify_provider_transport

    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    config.providers["custom_openai"] = {
        "api_base": "https://gateway.example/v1",
        "api_mode": "chat_completions",
        "api_key": "secret-for-test",
    }
    captured = []

    def unsupported(request, timeout):
        captured.append((request, timeout))
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(
        "infrastructure.models.catalog.open_provider_request",
        unsupported,
    )

    result = verify_provider_transport("custom_openai", config)

    assert result["status"] == "active"
    assert result["transport_status"] == "reachable"
    assert captured[0][0].method == "GET"
    assert captured[0][0].data is None


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def read(self, _amount=None):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_discovers_ollama_models(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        lambda request, timeout: FakeResponse(
            {"models": [{"name": "qwen:small"}, {"model": "vision:model"}]}
        ),
    )

    models = discover_provider_models("ollama", config)

    assert [model.model_id for model in models] == [
        "ollama/qwen:small",
        "ollama/vision:model",
    ]


def test_discovers_openai_compatible_models_with_bearer_header(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    config.providers["openai"]["api_key"] = "local-test-key"
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(request)
        return FakeResponse({"data": [{"id": "model-b"}, {"id": "model-a"}]})

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        fake_urlopen,
    )

    models = discover_provider_models("openai", config)

    assert [model.name for model in models] == ["model-a", "model-b"]
    assert captured[0].headers["Authorization"] == "Bearer local-test-key"


def test_curated_provider_discovery_keeps_broad_inventory_and_marks_core_models(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    curated_model = str(config.providers["openai"]["bundled_models"][0])

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        lambda request, timeout: FakeResponse(
            {
                "data": [
                    {"id": "internal-platform-model"},
                    {"id": curated_model},
                    {"id": "another-unrelated-model"},
                ]
            }
        ),
    )

    result = discover_provider_models_result(
        "openai",
        config,
        allow_configured_fallback=False,
    )

    assert [model.name for model in result.models] == [
        "another-unrelated-model",
        curated_model,
        "internal-platform-model",
    ]
    assert [model.curated for model in result.models] == [False, True, False]
    assert result.complete is True
    assert result.authoritative is True


def test_curated_provider_keeps_inventory_when_no_id_matches_core_list(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        lambda request, timeout: FakeResponse(
            {"data": [{"id": "unknown-platform-model"}]}
        ),
    )

    result = discover_provider_models_result(
        "openai",
        config,
        allow_configured_fallback=False,
    )

    assert [model.name for model in result.models] == ["unknown-platform-model"]
    assert result.models[0].curated is False
    assert result.authoritative is True


def test_custom_openai_discovery_uses_gateway_models_without_requiring_manual_ids(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    captured = []

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        lambda request, timeout: (
            captured.append(request),
            FakeResponse(
                {
                    "data": [{"id": "gateway-model"}, {"id": "another-gateway-model"}],
                }
            ),
        )[1],
    )

    result = discover_provider_models_result(
        "custom_openai",
        config,
        allow_configured_fallback=False,
    )

    assert [model.name for model in result.models] == [
        "another-gateway-model",
        "gateway-model",
    ]
    assert all(not model.curated for model in result.models)
    assert captured[0].full_url.endswith("/models")
    assert result.source == "provider_models"
    assert result.authoritative is True


def test_catalog_only_discovery_never_calls_generic_models_endpoint(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    config.providers["volc_connection"] = {
        "catalog_id": "volcengine_coding_plan",
        "discovery_strategy": "catalog_only",
        "bundled_models": ["curated-a", "curated-b"],
        "api_base": "https://ark.example/v1",
        "api_mode": "chat_completions",
    }

    def must_not_request(*_args, **_kwargs):
        raise AssertionError("catalog_only must not request /models")

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        must_not_request,
    )

    result = discover_provider_models_result("volc_connection", config)

    assert [item.name for item in result.models] == ["curated-a", "curated-b"]
    assert result.source == "bundled_catalog"
    assert result.complete is True
    assert result.authoritative is True


def test_volcengine_coding_plan_reads_restricted_models_inventory(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    config.providers["volc_connection"] = {
        "catalog_id": "volcengine_coding_plan",
        "discovery_strategy": "provider_adapter",
        "bundled_models": ["core-model"],
        "api_base": "https://ark.example/api/coding/v3",
        "api_mode": "chat_completions",
        "api_key": "coding-secret",
    }
    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return FakeResponse(
            {"data": [{"id": "core-model"}, {"id": "live-extra-model"}]}
        )

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        fake_urlopen,
    )

    result = discover_provider_models_result(
        "volc_connection", config, allow_configured_fallback=False
    )

    assert [item.name for item in result.models] == [
        "core-model",
        "live-extra-model",
    ]
    assert [item.curated for item in result.models] == [True, False]
    assert result.source == "provider_models"
    assert result.complete is True
    assert result.authoritative is True
    assert captured[0][0].full_url == "https://ark.example/api/coding/v3/models"
    assert captured[0][0].headers["Authorization"] == "Bearer coding-secret"


def test_volcengine_coding_plan_does_not_treat_general_ark_models_as_entitlement(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    config.providers["volc_connection"] = {
        "catalog_id": "volcengine_coding_plan",
        "discovery_strategy": "provider_adapter",
        "bundled_models": ["core-model"],
        "api_base": "https://ark.example/api/v3",
        "api_mode": "chat_completions",
    }

    def must_not_request(*_args, **_kwargs):
        raise AssertionError("general Ark endpoint must not be used for Coding Plan")

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        must_not_request,
    )

    result = discover_provider_models_result(
        "volc_connection", config, allow_configured_fallback=False
    )

    assert result.models == ()
    assert result.complete is False
    assert result.authoritative is False


def test_incomplete_model_discovery_fallback_cannot_be_authoritative(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    config.providers["gateway"] = {
        "catalog_id": "custom_openai",
        "discovery_strategy": "standard_models",
        "api_base": "https://gateway.example/v1",
        "api_mode": "chat_completions",
        "models": ["manual-a"],
    }

    def unavailable(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", {}, None)

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        unavailable,
    )

    result = discover_provider_models_result("gateway", config)

    assert [item.name for item in result.models] == ["manual-a"]
    assert result.complete is False
    assert result.authoritative is False


def test_batch_model_validation_uses_formal_call_path_and_collects_failures(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    calls = []

    def fake_call(config, provider, model, messages, temperature, max_tokens):
        calls.append((provider, model, temperature, max_tokens))
        if model == "broken":
            raise RuntimeError("model unavailable")
        return "OK"

    runner = ProviderValidationRunner(config, model_caller=fake_call)
    suite = runner.verify_models("ollama", ["working", "broken"])

    assert calls == [
        ("ollama", "working", 0.0, 8),
        ("ollama", "broken", 0.0, 8),
    ]
    assert suite.results[0].status is CheckStatus.PASSED
    assert suite.results[1].status is CheckStatus.FAILED
    assert suite.passed is False


def test_model_discovery_failure_becomes_check_result(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()

    def fail(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        fail,
    )
    suite = ProviderValidationRunner(config).verify_models("ollama")

    assert suite.results[0].status is CheckStatus.FAILED
    assert "offline" in suite.results[0].message


def test_discovery_uses_manual_models_when_models_endpoint_is_unavailable(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    config.providers["custom_gateway"] = {
        "api_base": "https://gateway.example/v1",
        "api_mode": "chat_completions",
        "auth_type": "bearer",
        "models": ["model-a", "model-b"],
    }

    def unsupported(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        unsupported,
    )

    models = discover_provider_models("custom_gateway", config)

    assert [model.name for model in models] == ["model-a", "model-b"]
    assert {model.source for model in models} == {"configured"}


def test_xfyun_coding_plan_uses_official_model_alias_when_listing_is_unavailable(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = model_execution_config()
    config.providers["custom_openai"]["api_base"] = (
        "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2"
    )
    config.providers["custom_openai"]["test_model"] = "custom-model"

    def unsupported(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(
        "infrastructure.models.validation.provider_validation.open_provider_request",
        unsupported,
    )

    models = discover_provider_models("custom_openai", config)

    assert [model.name for model in models] == ["astron-code-latest"]
    assert models[0].source == "configured"
