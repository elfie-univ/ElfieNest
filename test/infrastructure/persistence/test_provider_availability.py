from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.validation.serving_food import ServingFoodIndex
from infrastructure.persistence.provider_availability import ProviderAvailabilityQuery


class _Storage:
    def __init__(self, connection: ProviderConnection) -> None:
        self.connections = {connection.connection_id: connection}

    def load_connections(self):
        return self.connections


class _Reports:
    def __init__(self, observations) -> None:
        self.observations = tuple(observations)

    def observations_for_subject(self, subject_kind, subject_id):
        return tuple(
            item
            for item in self.observations
            if item.subject_kind == subject_kind and item.subject_id == subject_id
        )


def _observation(
    subject_id: str,
    *,
    code: str | None = None,
    category: str | None = None,
    fingerprint: str | None = None,
):
    details = {
        "reason_code": code,
        "evidence_source": "production",
        "workload_kind": "production",
    }
    if fingerprint is not None:
        details["config_fingerprint"] = fingerprint
    return type(
        "Observation",
        (),
        {
            "observation_id": 1,
            "subject_kind": "model",
            "subject_id": subject_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "status": "passed" if code is None else "failed",
            "error_category": category,
            "details": details,
        },
    )()


def test_query_is_exact_endpoint_scoped_and_projects_connection_blocks() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://example.test",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(
            ProviderModelRecord(
                "main",
                supports_vision=False,
                supports_tools=True,
                source="manual",
            ),
            ProviderModelRecord("sibling", source="manual"),
        ),
    )
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports((_observation("cloud_0001/main", code="billing_blocked", category="billing"),)),
        serving_index=lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(),
        ),
    )

    main = query.get("cloud_0001/main")
    sibling = query.get("cloud_0001/sibling")

    assert main.status == "unavailable"
    assert main.provider_status == "unavailable"
    assert main.capabilities[0].name == "tools"
    assert main.capabilities[0].state == "supported"
    assert next(item for item in main.capabilities if item.name == "vision").state == "unsupported"
    assert sibling.status == "unavailable"
    assert sibling.reason_code == "billing_blocked"


def test_query_returns_unknown_without_evidence_and_does_not_call_network() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://example.test",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(ProviderModelRecord("main", source="manual"),),
    )
    query = ProviderAvailabilityQuery(_Storage(connection), _Reports(()))

    result = query.get("cloud_0001/main")

    assert result.status == "unknown"
    assert result.reason_code == "no_health_evidence"


def test_query_rejects_observations_from_an_old_configuration_fingerprint() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://example.test",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(ProviderModelRecord("main", source="manual"),),
    )
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports((_observation("cloud_0001/main", fingerprint="new"),)),
        config_fingerprint=lambda _connection: "current",
    )

    result = query.get("cloud_0001/main")

    assert result.status == "unknown"
    assert result.reason_code == "no_health_evidence"


def test_active_probe_is_single_flight_and_cooldown_limited() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://example.test",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(ProviderModelRecord("main", source="manual"),),
    )
    calls = 0
    calls_lock = threading.Lock()

    def probe(_reference: str) -> None:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)

    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports(()),
        active_probe=probe,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda _index: query.ensure(
                    "cloud_0001/main", allow_probe=True
                ),
                (1, 2),
            )
        )
    query.ensure("cloud_0001/main", allow_probe=True)

    assert len(results) == 2
    assert calls == 1
