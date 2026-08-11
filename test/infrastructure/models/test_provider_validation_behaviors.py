from __future__ import annotations

import asyncio
import urllib.error
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from ai_runtime.storage.secrets import set_connection_secret
from ai_runtime.storage.validation_reports import read_latest_model_validation
from app.features.configuration import (
    StoredProviderConnection,
    StoredProviderModel,
)
from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.models.provider_validation_policy import (
    choose_validation_mode,
    connection_validation_fingerprint,
)
from infrastructure.models.provider_validation_runtime import runtime_projection
from infrastructure.models.provider_validation_service import validate_connection


def _full_report(connection, checked_at: str) -> dict[str, object]:
    model_ids = tuple(
        model.endpoint_model_id
        for model in connection.models
        if not model.hidden and not model.retired
    )
    return {
        "status": "passed",
        "checked_at": checked_at,
        "metadata": {
            "validation_mode": "full",
            "full_run_id": "run-full",
            "full_checked_at": checked_at,
            "config_fingerprint": connection_validation_fingerprint(connection),
            "model_ids": list(model_ids),
        },
    }


def test_validation_policy_reuses_a_full_result_for_24_hours() -> None:
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Cache",
        models=(ProviderModelRecord(endpoint_model_id="model-a"),),
    )

    decision = choose_validation_mode(
        connection,
        _full_report(connection, "2026-08-04T12:00:00+00:00"),
        now=datetime.fromisoformat("2026-08-05T11:59:59+00:00"),
    )

    assert decision.mode == "cached"
    assert decision.source_run_id == "run-full"


def test_validation_policy_reuses_a_recent_heartbeat_for_24_hours() -> None:
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Heartbeat cache",
        models=(ProviderModelRecord(endpoint_model_id="model-a"),),
    )
    report = _full_report(connection, "2026-07-20T12:00:00+00:00")
    report["checked_at"] = "2026-07-20T18:00:00+00:00"
    metadata = report["metadata"]
    metadata.update(
        {
            "validation_mode": "heartbeat",
            "heartbeat_checked_at": "2026-07-20T18:00:00+00:00",
            "heartbeat_status": "passed",
        }
    )

    decision = choose_validation_mode(
        connection,
        report,
        now=datetime.fromisoformat("2026-07-21T17:59:59+00:00"),
    )

    assert decision.mode == "cached"


def test_validation_policy_uses_one_heartbeat_before_30_days() -> None:
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Heartbeat",
        models=(
            ProviderModelRecord(endpoint_model_id="model-a"),
            ProviderModelRecord(endpoint_model_id="model-b"),
        ),
    )

    decision = choose_validation_mode(
        connection,
        _full_report(connection, "2026-07-10T12:00:00+00:00"),
        now=datetime.fromisoformat("2026-07-20T12:00:01+00:00"),
    )

    assert decision.mode == "heartbeat"
    assert decision.representative_model_id == "model-a"


def test_validation_policy_requires_full_run_after_30_days_or_model_change() -> None:
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Expired",
        models=(ProviderModelRecord(endpoint_model_id="model-a"),),
    )

    expired = choose_validation_mode(
        connection,
        _full_report(connection, "2026-07-01T12:00:00+00:00"),
        now=datetime.fromisoformat("2026-08-05T12:00:01+00:00"),
    )
    changed = choose_validation_mode(
        replace(
            connection,
            models=(
                ProviderModelRecord(endpoint_model_id="model-a"),
                ProviderModelRecord(endpoint_model_id="model-b"),
            ),
        ),
        _full_report(connection, "2026-08-05T11:00:00+00:00"),
        now=datetime.fromisoformat("2026-08-05T12:00:01+00:00"),
    )

    assert expired.mode == "full"
    assert changed.mode == "full"


def test_connection_fingerprint_ignores_another_connection_secret_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    jdcloud = ProviderConnection(
        connection_id="jdcloud_coding_plan_0001",
        catalog_id="jdcloud_coding_plan",
        alias="JD Cloud",
        models=(ProviderModelRecord(endpoint_model_id="GLM-5"),),
    )
    deepseek = ProviderConnection(
        connection_id="deepseek_0001",
        catalog_id="deepseek",
        alias="DeepSeek",
        models=(ProviderModelRecord(endpoint_model_id="deepseek-chat"),),
    )

    set_connection_secret(jdcloud.connection_id, "jd-key")
    jdcloud_before = connection_validation_fingerprint(jdcloud)
    deepseek_before = connection_validation_fingerprint(deepseek)
    set_connection_secret(deepseek.connection_id, "deepseek-key")

    assert connection_validation_fingerprint(jdcloud) == jdcloud_before
    assert connection_validation_fingerprint(deepseek) != deepseek_before


def test_runtime_projection_uses_connection_id_for_builtin_connection() -> None:
    connection = ProviderConnection(
        connection_id="jdcloud_coding_plan_0001",
        catalog_id="jdcloud_coding_plan",
        alias="JD Cloud",
        models=(ProviderModelRecord(endpoint_model_id="GLM-5"),),
    )

    runtime_id, _config = runtime_projection(connection)

    assert runtime_id == connection.connection_id


def test_single_validation_checks_configured_models_without_provider_models_probe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Configured models",
        api_base="https://gateway.example/v1",
        models=(
            ProviderModelRecord(endpoint_model_id="model-a"),
            ProviderModelRecord(endpoint_model_id="model-b"),
        ),
    )
    ProviderConnectionStore().replace(connection)
    calls: list[str] = []

    def model_check(connection, model_id, runtime_projection):
        _ = connection, runtime_projection
        calls.append(model_id)
        return {
            "status": "passed",
            "latency_ms": 10.0,
            "latency_class": "fast",
            "error": None,
        }

    with patch(
        "infrastructure.models.provider_validation_checks.run_connection_model_check",
        side_effect=model_check,
    ):
        payload = asyncio.run(
            validate_connection(
                connection,
                runtime_projection=runtime_projection,
            )
        )

    assert calls == ["model-a", "model-b"]
    assert payload["status"] == "passed"
    assert payload["validation_mode"] == "full"
    assert payload["model_count"] == 2


def test_single_validation_reuses_recent_full_result_without_new_model_requests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Cached validation",
        api_base="https://gateway.example/v1",
        models=(ProviderModelRecord(endpoint_model_id="model-a"),),
    )
    ProviderConnectionStore().replace(connection)

    def model_check(connection, model_id, runtime_projection):
        _ = connection, model_id, runtime_projection
        return {
            "status": "passed",
            "latency_ms": 10.0,
            "latency_class": "fast",
            "error": None,
        }

    with patch(
        "infrastructure.models.provider_validation_checks.run_connection_model_check",
        side_effect=model_check,
    ) as check:
        first = asyncio.run(
            validate_connection(
                connection,
                runtime_projection=runtime_projection,
            )
        )
        check.reset_mock()
        second = asyncio.run(
            validate_connection(
                connection,
                runtime_projection=runtime_projection,
            )
        )

    assert first["validation_mode"] == "full"
    assert second["validation_mode"] == "cached"
    assert second["cache_hit"] is True
    check.assert_not_called()


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

    runtime_id, config = runtime_projection(connection)

    assert runtime_id == connection.connection_id
    assert config.providers[runtime_id]["test_model"] == "GLM-5"


def test_jdcloud_health_check_falls_back_to_configured_model(
    monkeypatch,
) -> None:
    from infrastructure.models.catalog import verify_provider

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
        "infrastructure.models.catalog.open_provider_request",
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
    from infrastructure.models.catalog import verify_provider

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
        "infrastructure.models.catalog.open_provider_request",
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

    def model_check(connection, model_id, runtime_projection):
        _ = connection, runtime_projection
        status = "passed" if model_id == "passed-model" else "failed"
        return {
            "status": status,
            "latency_ms": 120.0 if status == "passed" else 240.0,
            "latency_class": "fast",
            "error": None if status == "passed" else "model rejected",
        }

    with patch(
        "infrastructure.models.provider_validation_checks.run_connection_model_check",
        side_effect=model_check,
    ):
        payload = asyncio.run(
            ProviderModelsAdapter().validate_all(
                (
                    StoredProviderConnection(
                        connection_id=connection.connection_id,
                        catalog_id=connection.catalog_id,
                        alias=connection.alias,
                        api_base=connection.api_base,
                        api_mode="chat_completions",
                        auth_type="bearer",
                        credential_ref=connection.credential_ref,
                        models=tuple(
                            StoredProviderModel(
                                model.endpoint_model_id,
                                model.display_name,
                                source=model.source,
                                hidden=model.hidden,
                                retired=model.retired,
                            )
                            for model in connection.models
                        ),
                    ),
                ),
                _ConnectedRequest().is_disconnected,
            )
        )

    subjects = [item.subject for item in payload.results]
    assert "model:custom_openai_0001/passed-model" in subjects
    assert "model:custom_openai_0001/failed-model" in subjects
    assert "model:custom_openai_0001/hidden-model" not in subjects
    assert (
        read_latest_model_validation("custom_openai_0001", "passed-model")["latency_ms"]
        == 120.0
    )
    assert (
        read_latest_model_validation("custom_openai_0001", "failed-model")["status"]
        == "failed"
    )
