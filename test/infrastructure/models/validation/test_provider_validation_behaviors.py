from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.features.configuration import (
    StoredProviderConnection,
    StoredProviderModel,
)
from infrastructure.models.validation.provider_validation_execution import (
    model_execution_projection,
)
from infrastructure.models.validation.provider_validation_policy import (
    choose_validation_mode,
    connection_validation_fingerprint,
)
from infrastructure.models.validation.provider_validation_service import (
    validate_connection,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_system_defaults,
)
from infrastructure.persistence.configuration.secrets import (
    resolve_secret,
    set_connection_secret,
)
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.persistence.reports.report_repository import ReportRepository
from infrastructure.persistence.reports.validation_reports import (
    read_latest_model_validation,
)
from test.support.provider import provider_models_adapter

PROVIDER_CATALOG = load_provider_catalog()
SYSTEM_DEFAULTS = load_system_defaults()


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
            "config_fingerprint": connection_validation_fingerprint(
                connection, secret_resolver=resolve_secret
            ),
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
        catalog=PROVIDER_CATALOG,
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
        catalog=PROVIDER_CATALOG,
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
        catalog=PROVIDER_CATALOG,
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
        catalog=PROVIDER_CATALOG,
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
        catalog=PROVIDER_CATALOG,
        now=datetime.fromisoformat("2026-08-05T12:00:01+00:00"),
    )

    assert expired.mode == "full"
    assert changed.mode == "full"


def test_connection_fingerprint_ignores_another_connection_secret_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    volcengine = ProviderConnection(
        connection_id="volcengine_coding_plan_0001",
        catalog_id="volcengine_coding_plan",
        alias="Volcengine",
        models=(ProviderModelRecord(endpoint_model_id="deepseek-v4-pro"),),
    )
    deepseek = ProviderConnection(
        connection_id="deepseek_0001",
        catalog_id="deepseek",
        alias="DeepSeek",
        models=(ProviderModelRecord(endpoint_model_id="deepseek-chat"),),
    )

    set_connection_secret(volcengine.connection_id, "volc-key")
    volcengine_before = connection_validation_fingerprint(
        volcengine, secret_resolver=resolve_secret
    )
    deepseek_before = connection_validation_fingerprint(
        deepseek, secret_resolver=resolve_secret
    )
    set_connection_secret(deepseek.connection_id, "deepseek-key")

    assert (
        connection_validation_fingerprint(volcengine, secret_resolver=resolve_secret)
        == volcengine_before
    )
    assert (
        connection_validation_fingerprint(deepseek, secret_resolver=resolve_secret)
        != deepseek_before
    )


def test_model_execution_projection_uses_connection_id_for_builtin_connection() -> None:
    connection = ProviderConnection(
        connection_id="volcengine_coding_plan_0001",
        catalog_id="volcengine_coding_plan",
        alias="Volcengine",
        models=(ProviderModelRecord(endpoint_model_id="deepseek-v4-pro"),),
    )

    execution_id, _config = model_execution_projection(
        connection,
        catalog=PROVIDER_CATALOG,
        system_defaults=SYSTEM_DEFAULTS,
    )

    assert execution_id == connection.connection_id


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
    reports = ReportStorageAdapter(ReportRepository())
    calls: list[str] = []

    def model_check(connection, model_id, model_execution_projection):
        _ = connection, model_execution_projection
        calls.append(model_id)
        return {
            "status": "passed",
            "latency_ms": 10.0,
            "latency_class": "fast",
            "error": None,
        }

    with patch(
        "infrastructure.models.validation.provider_validation_checks.run_connection_model_check",
        side_effect=model_check,
    ):
        payload = asyncio.run(
            validate_connection(
                connection,
                catalog=PROVIDER_CATALOG,
                model_execution_projection=model_execution_projection,
                reports=reports,
                secret_resolver=resolve_secret,
            )
        )

    assert calls == ["model-a", "model-b"]
    assert payload["status"] == "passed"
    assert payload["validation_mode"] == "full"
    assert payload["model_count"] == 2


def test_connection_block_stops_the_remaining_model_checks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Blocked account",
        api_base="https://gateway.example/v1",
        models=(
            ProviderModelRecord(endpoint_model_id="model-a"),
            ProviderModelRecord(endpoint_model_id="model-b"),
        ),
    )
    reports = ReportStorageAdapter(ReportRepository())
    calls: list[str] = []

    def model_check(connection, model_id, model_execution_projection):
        _ = connection, model_execution_projection
        calls.append(model_id)
        return {
            "status": "failed",
            "latency_ms": 10.0,
            "latency_class": "fast",
            "error": "账号余额不足",
            "error_code": "billing_blocked",
            "error_scope": "connection",
            "error_category": "billing",
        }

    with patch(
        "infrastructure.models.validation.provider_validation_checks.run_connection_model_check",
        side_effect=model_check,
    ):
        payload = asyncio.run(
            validate_connection(
                connection,
                catalog=PROVIDER_CATALOG,
                model_execution_projection=model_execution_projection,
                reports=reports,
                secret_resolver=resolve_secret,
            )
        )

    assert calls == ["model-a"]
    assert payload["status"] == "failed"
    assert payload["model_count"] == 1


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
    reports = ReportStorageAdapter(ReportRepository())

    def model_check(connection, model_id, model_execution_projection):
        _ = connection, model_id, model_execution_projection
        return {
            "status": "passed",
            "latency_ms": 10.0,
            "latency_class": "fast",
            "error": None,
        }

    with patch(
        "infrastructure.models.validation.provider_validation_checks.run_connection_model_check",
        side_effect=model_check,
    ) as check:
        first = asyncio.run(
            validate_connection(
                connection,
                catalog=PROVIDER_CATALOG,
                model_execution_projection=model_execution_projection,
                reports=reports,
                secret_resolver=resolve_secret,
            )
        )
        check.reset_mock()
        second = asyncio.run(
            validate_connection(
                connection,
                catalog=PROVIDER_CATALOG,
                model_execution_projection=model_execution_projection,
                reports=reports,
                secret_resolver=resolve_secret,
            )
        )

    assert first["validation_mode"] == "full"
    assert second["validation_mode"] == "cached"
    assert second["cache_hit"] is True
    check.assert_not_called()


def test_model_execution_projection_keeps_volcengine_profile_test_model() -> None:
    connection = ProviderConnection(
        connection_id="volcengine_coding_plan_0001",
        catalog_id="volcengine_coding_plan",
        alias="Volcengine",
        models=(
            ProviderModelRecord(endpoint_model_id="deepseek-v4-pro"),
            ProviderModelRecord(endpoint_model_id="deepseek-v3.2"),
        ),
    )

    execution_id, config = model_execution_projection(
        connection,
        catalog=PROVIDER_CATALOG,
        system_defaults=SYSTEM_DEFAULTS,
    )

    assert execution_id == connection.connection_id
    assert config.providers[execution_id]["test_model"] == "deepseek-v4-pro"


def test_model_execution_projection_keeps_endpoint_request_profile_shape() -> None:
    connection = ProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Custom",
        api_mode="chat_completions",
        models=(
            ProviderModelRecord(
                endpoint_model_id="model-a",
                request_profile_id="openai_chat_v1",
                request_profile_version=1,
            ),
        ),
    )

    execution_id, config = model_execution_projection(
        connection,
        catalog=PROVIDER_CATALOG,
        system_defaults=SYSTEM_DEFAULTS,
    )

    assert config.providers[execution_id]["model_profiles"] == {
        "model-a": {
            "request_profile_id": "openai_chat_v1",
            "request_profile_version": 1,
        }
    }


def test_volcengine_health_check_uses_configured_model_without_models_probe(
    monkeypatch,
) -> None:
    from infrastructure.models.catalog import verify_provider

    chat_response = MagicMock()
    chat_response.status = 200
    chat_response.__enter__ = MagicMock(return_value=chat_response)
    chat_response.__exit__ = MagicMock(return_value=False)
    requests = []

    def open_request(request, *, timeout):
        requests.append(request)
        return chat_response

    monkeypatch.setattr(
        "infrastructure.models.catalog.open_provider_request",
        open_request,
    )

    class Config:
        provider_catalog = PROVIDER_CATALOG
        providers = {
            "volcengine_coding_plan": {
                "api_base": "https://volc.example/api/coding/v3",
                "api_key": "test-key",
                "api_mode": "chat_completions",
                "test_model": "deepseek-v4-pro",
            }
        }

    result = verify_provider("volcengine_coding_plan", Config())

    assert result["status"] == "active"
    assert [request.full_url for request in requests] == [
        "https://volc.example/api/coding/v3/chat/completions",
    ]
    assert b'"model": "deepseek-v4-pro"' in requests[0].data


def test_volcengine_health_check_reports_unsupported_model(
    monkeypatch,
) -> None:
    from infrastructure.models.catalog import verify_provider

    chat_response = MagicMock()
    chat_response.status = 400
    chat_response.__enter__ = MagicMock(return_value=chat_response)
    chat_response.__exit__ = MagicMock(return_value=False)
    requests = []

    def open_request(request, *, timeout):
        requests.append(request)
        return chat_response

    monkeypatch.setattr(
        "infrastructure.models.catalog.open_provider_request",
        open_request,
    )

    class Config:
        provider_catalog = PROVIDER_CATALOG
        providers = {
            "volcengine_coding_plan": {
                "api_base": "https://volc.example/api/coding/v3",
                "api_key": "test-key",
                "api_mode": "chat_completions",
                "test_model": "not-a-volc-model",
            }
        }

    result = verify_provider("volcengine_coding_plan", Config())

    assert result["status"] == "inactive"
    assert result["error"] == "HTTP 400（测试模型 not-a-volc-model）"


def test_provider_health_rejects_missing_catalog_instead_of_using_generic_probe(
    monkeypatch,
) -> None:
    from infrastructure.models.catalog import verify_provider

    def unexpected_request(*args, **kwargs):
        raise AssertionError("provider health must fail before any generic probe")

    monkeypatch.setattr(
        "infrastructure.models.catalog.open_provider_request",
        unexpected_request,
    )

    class Config:
        providers = {
            "volcengine_coding_plan": {
                "api_base": "https://volc.example/api/coding/v3",
                "api_key": "test-key",
                "api_mode": "chat_completions",
                "test_model": "deepseek-v4-pro",
            }
        }

    with pytest.raises(ValueError, match="injected provider catalog"):
        verify_provider("volcengine_coding_plan", Config())


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

    def model_check(connection, model_id, model_execution_projection):
        _ = connection, model_execution_projection
        status = "passed" if model_id == "passed-model" else "failed"
        return {
            "status": status,
            "latency_ms": 120.0 if status == "passed" else 240.0,
            "latency_class": "fast",
            "error": None if status == "passed" else "model rejected",
        }

    with patch(
        "infrastructure.models.validation.provider_validation_checks.run_connection_model_check",
        side_effect=model_check,
    ):
        payload = asyncio.run(
            provider_models_adapter().validate_all(
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
