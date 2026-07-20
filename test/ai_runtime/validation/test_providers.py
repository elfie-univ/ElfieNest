import json
import urllib.error

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.validation.models import CheckStatus
from ai_runtime.validation.providers import (
    ProviderValidationRunner,
    classify_latency,
    discover_provider_models,
)


def test_latency_is_classified_for_reports():
    assert classify_latency(500) == "fast"
    assert classify_latency(2_000) == "normal"
    assert classify_latency(8_000) == "slow"


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_discovers_ollama_models(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    monkeypatch.setattr(
        "ai_runtime.validation.providers.urllib.request.urlopen",
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
    config = LLMRuntimeConfig()
    config.providers["openai"]["api_key"] = "local-test-key"
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(request)
        return FakeResponse({"data": [{"id": "model-b"}, {"id": "model-a"}]})

    monkeypatch.setattr(
        "ai_runtime.validation.providers.urllib.request.urlopen", fake_urlopen
    )

    models = discover_provider_models("openai", config)

    assert [model.name for model in models] == ["model-a", "model-b"]
    assert captured[0].headers["Authorization"] == "Bearer local-test-key"


def test_batch_model_validation_uses_formal_call_path_and_collects_failures(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
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
    config = LLMRuntimeConfig()

    def fail(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("ai_runtime.validation.providers.urllib.request.urlopen", fail)
    suite = ProviderValidationRunner(config).verify_models("ollama")

    assert suite.results[0].status is CheckStatus.FAILED
    assert "offline" in suite.results[0].message


def test_discovery_uses_manual_models_when_models_endpoint_is_unavailable(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    config.providers["custom_gateway"] = {
        "api_base": "https://gateway.example/v1",
        "api_mode": "chat_completions",
        "auth_type": "bearer",
        "models": ["model-a", "model-b"],
    }

    def unsupported(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(
        "ai_runtime.validation.providers.urllib.request.urlopen", unsupported
    )

    models = discover_provider_models("custom_gateway", config)

    assert [model.name for model in models] == ["model-a", "model-b"]
    assert {model.source for model in models} == {"configured"}


def test_xfyun_coding_plan_uses_official_model_alias_when_listing_is_unavailable(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    config.providers["custom_openai"]["api_base"] = (
        "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2"
    )
    config.providers["custom_openai"]["test_model"] = "custom-model"

    def unsupported(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(
        "ai_runtime.validation.providers.urllib.request.urlopen", unsupported
    )

    models = discover_provider_models("custom_openai", config)

    assert [model.name for model in models] == ["astron-code-latest"]
    assert models[0].source == "configured"
