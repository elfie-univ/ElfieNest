from __future__ import annotations

import asyncio
import urllib.error
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from ai_runtime.storage.validation_reports import read_latest_model_validation
from app.interfaces.api.provider_connection_model_routes import (
    validate_all_connection_models,
)
from app.interfaces.api.provider_connection_routes import _runtime_projection


def test_runtime_projection_keeps_jdcloud_profile_test_model() -> None:
    connection = ProviderConnection(
        connection_id="jdcloud_coding_plan_0001",
        catalog_id="jdcloud_coding_plan",
        alias="JD Cloud",
        models=(
            ProviderModelRecord(endpoint_model_id="DeepSeek-V3.2"),
            ProviderModelRecord(endpoint_model_id="GLM-5"),
        ),
    )

    runtime_id, config = _runtime_projection(connection)

    assert runtime_id == "jdcloud_coding_plan"
    assert config.providers[runtime_id]["test_model"] == "GLM-5"


def test_jdcloud_health_check_falls_back_to_configured_model(
    monkeypatch,
) -> None:
    from ai_runtime.models.catalog import verify_provider

    first_error = urllib.error.HTTPError(
        "https://jd.example/models",
        404,
        "Not Found",
        {},
        None,
    )
    chat_response = MagicMock()
    chat_response.status = 200
    chat_response.__enter__ = MagicMock(return_value=chat_response)
    chat_response.__exit__ = MagicMock(return_value=False)
    requests = []

    def open_request(request, *, timeout):
        requests.append(request)
        if len(requests) == 1:
            raise first_error
        return chat_response

    monkeypatch.setattr(
        "ai_runtime.models.catalog.open_provider_request",
        open_request,
    )

    class Config:
        providers = {
            "jdcloud_coding_plan": {
                "api_base": "https://jd.example/v1",
                "api_key": "test-key",
                "api_mode": "chat_completions",
                "test_model": "GLM-5",
            }
        }

    result = verify_provider("jdcloud_coding_plan", Config())

    assert result["status"] == "active"
    assert [request.full_url for request in requests] == [
        "https://jd.example/v1/models",
        "https://jd.example/v1/chat/completions",
    ]
    assert b'"model": "GLM-5"' in requests[1].data


def test_jdcloud_health_check_reports_unsupported_model(
    monkeypatch,
) -> None:
    from ai_runtime.models.catalog import verify_provider

    list_error = urllib.error.HTTPError(
        "https://jd.example/v1/models",
        404,
        "Not Found",
        {},
        None,
    )
    chat_response = MagicMock()
    chat_response.status = 400
    chat_response.__enter__ = MagicMock(return_value=chat_response)
    chat_response.__exit__ = MagicMock(return_value=False)
    requests = []

    def open_request(request, *, timeout):
        requests.append(request)
        if len(requests) == 1:
            raise list_error
        return chat_response

    monkeypatch.setattr(
        "ai_runtime.models.catalog.open_provider_request",
        open_request,
    )

    class Config:
        providers = {
            "jdcloud_coding_plan": {
                "api_base": "https://jd.example/v1",
                "api_key": "test-key",
                "api_mode": "chat_completions",
                "test_model": "not-a-jd-model",
            }
        }

    result = verify_provider("jdcloud_coding_plan", Config())

    assert result["status"] == "inactive"
    assert result["error"] == "HTTP 400（测试模型 not-a-jd-model）"


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


def test_validate_all_writes_each_enabled_model_and_skips_hidden(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Batch",
        models=(
            ProviderModelRecord(endpoint_model_id="passed-model"),
            ProviderModelRecord(endpoint_model_id="failed-model"),
            ProviderModelRecord(endpoint_model_id="hidden-model", hidden=True),
        ),
    )
    ProviderConnectionStore().replace(connection)

    async def benchmark(combination, semaphore):
        _ = semaphore
        status = "passed" if combination.model_id == "passed-model" else "failed"
        return {
            "status": status,
            "latency_ms": 120.0 if status == "passed" else 240.0,
            "latency_class": "fast",
            "error": None if status == "passed" else "model rejected",
        }

    with (
        patch(
            "app.interfaces.api.provider_connection_model_routes._verify_connection_in_run",
            new=AsyncMock(
                return_value={
                    "status": "passed",
                    "checked_at": "2026-08-03T01:00:00+00:00",
                    "latency_ms": 40.0,
                    "error": None,
                }
            ),
        ),
        patch(
            "app.interfaces.api.provider_connection_model_routes.bounded_benchmark",
            side_effect=benchmark,
        ),
    ):
        payload = asyncio.run(
            validate_all_connection_models(_ConnectedRequest(), owner={})
        )

    subjects = [item["subject"] for item in payload["results"]]
    assert "model:custom_openai_0001/passed-model" in subjects
    assert "model:custom_openai_0001/failed-model" in subjects
    assert "model:custom_openai_0001/hidden-model" not in subjects
    assert read_latest_model_validation(
        "custom_openai_0001", "passed-model"
    )["latency_ms"] == 120.0
    assert read_latest_model_validation(
        "custom_openai_0001", "failed-model"
    )["status"] == "failed"
