from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.validation.core_validation_scheduler import (
    CoreValidationScheduler,
)
from infrastructure.models.validation.serving_food import (
    CoreEndpointRoute,
    ServingFoodIndex,
)
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
    subject_kind: str = "model",
    evidence_kind: str | None = None,
):
    details = {
        "reason_code": code,
        "evidence_source": "production",
        "workload_kind": "production",
    }
    if fingerprint is not None:
        details["config_fingerprint"] = fingerprint
    if evidence_kind is not None:
        details["evidence_kind"] = evidence_kind
    return type(
        "Observation",
        (),
        {
            "observation_id": 1,
            "subject_kind": subject_kind,
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
        _Reports(
            (
                _observation(
                    "cloud_0001/main", code="billing_blocked", category="billing"
                ),
            )
        ),
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
    assert (
        next(item for item in main.capabilities if item.name == "vision").state
        == "unsupported"
    )
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


def test_hidden_and_source_missing_models_do_not_poison_provider_status() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://example.test",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(
            ProviderModelRecord("main", source="manual"),
            ProviderModelRecord("hidden", source="manual", hidden=True),
            ProviderModelRecord(
                "gone", source="official", discovery_state="source_missing"
            ),
        ),
    )
    observations = (
        _observation("cloud_0001/main"),
        _observation("cloud_0001/hidden", code="model_not_found"),
        _observation("cloud_0001/gone", code="model_not_found"),
    )

    query = ProviderAvailabilityQuery(_Storage(connection), _Reports(observations))

    assert query.get("cloud_0001/main").provider_status == "healthy"


def test_hidden_model_referenced_by_serving_food_stays_in_core_health_scope() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://example.test",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(ProviderModelRecord("hidden", source="manual", hidden=True),),
    )
    reference = "cloud_0001/hidden"
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports((_observation(reference),)),
        serving_index=lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(
                CoreEndpointRoute(reference, ("food_common",), ("primary",)),
            ),
        ),
    )

    result = query.get(reference)

    assert result.is_core is True
    assert result.status == "available"
    assert result.provider_status == "healthy"


def test_source_missing_model_referenced_by_serving_food_is_explicitly_unavailable() -> (
    None
):
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
                "gone", source="official", discovery_state="source_missing"
            ),
        ),
    )
    reference = "cloud_0001/gone"
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports((_observation(reference),)),
        serving_index=lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(
                CoreEndpointRoute(reference, ("food_common",), ("primary",)),
            ),
        ),
    )

    result = query.get(reference)

    assert result.is_core is True
    assert result.status == "unavailable"
    assert result.reason_code == "source_missing"
    assert result.provider_status == "unavailable"


def test_provider_reachability_alone_does_not_make_empty_scope_healthy() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://example.test",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(ProviderModelRecord("hidden", source="manual", hidden=True),),
    )
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports(
            (
                _observation(
                    "cloud_0001",
                    subject_kind="provider",
                    evidence_kind="reachability",
                ),
            )
        ),
        serving_index=lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(),
        ),
    )

    result = query.get("cloud_0001/hidden")

    assert result.provider_status == "unknown"


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
                lambda _index: query.ensure("cloud_0001/main", allow_probe=True),
                (1, 2),
            )
        )
    query.ensure("cloud_0001/main", allow_probe=True)

    assert len(results) == 2
    assert calls == 1


def test_reachability_does_not_retry_a_deterministic_connection_block() -> None:
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

    def probe(_connection_id: str) -> None:
        nonlocal calls
        calls += 1

    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports(
            (
                _observation(
                    "cloud_0001",
                    code="billing_blocked",
                    category="billing",
                    subject_kind="provider",
                    evidence_kind="reachability",
                ),
            )
        ),
        active_reachability_probe=probe,
    )

    state = query.ensure_reachability("cloud_0001", allow_probe=True)

    assert state.status == "unavailable"
    assert state.reason_code == "billing_blocked"
    assert calls == 0


def test_active_capability_probe_uses_a_separate_single_flight_key() -> None:
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
    calls: list[tuple[str, str]] = []

    def probe(reference: str, capability: str) -> None:
        calls.append((reference, capability))

    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports(()),
        active_capability_probe=probe,
    )

    query.ensure(
        "cloud_0001/main",
        allow_probe=True,
        capability="vision",
    )

    assert calls == [("cloud_0001/main", "vision")]


def test_core_validation_entry_point_uses_current_serving_index(tmp_path) -> None:
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
    calls: list[tuple[str, str]] = []
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports(()),
        serving_index=lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(),
        ),
    )
    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        lambda reference, channel: calls.append((reference, channel)),
    )

    result = query.run_core_validation(scheduler)

    assert result.acquired is True
    assert calls == []


def test_core_validation_uses_role_evidence_not_text_health(tmp_path) -> None:
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
                supports_vision=True,
                source="manual",
            ),
        ),
    )
    model_ref = "cloud_0001/main"
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports((_observation(model_ref),)),
        serving_index=lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(
                CoreEndpointRoute(model_ref, ("food_common",), ("vision",)),
            ),
        ),
    )
    calls: list[tuple[str, str]] = []
    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        lambda reference, channel: calls.append((reference, channel)),
    )

    result = query.run_core_validation(scheduler)

    assert result.acquired is True
    assert calls == [(model_ref, "vision")]


def test_declared_capability_is_stable_and_does_not_trigger_paid_probe(
    tmp_path,
) -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="openai_api",
        alias="Cloud",
        api_base="https://example.test/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(
            ProviderModelRecord(
                "main",
                source="official",
                supports_vision=True,
                capability_evidence={"vision": "declared"},
            ),
        ),
    )
    model_ref = "cloud_0001/main"
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports((_observation(model_ref),)),
        serving_index=lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(
                CoreEndpointRoute(model_ref, ("food_common",), ("vision",)),
            ),
        ),
    )
    calls: list[tuple[str, str]] = []
    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        lambda reference, channel: calls.append((reference, channel)),
    )

    result = query.run_core_validation(scheduler)

    assert result.acquired is True
    assert calls == []


def test_accepted_capability_is_unknown_until_verified(tmp_path) -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="openai_api",
        alias="Cloud",
        api_base="https://example.test/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="CLOUD_KEY",
        models=(
            ProviderModelRecord(
                "main",
                source="official",
                supports_vision=True,
                capability_evidence={"vision": "accepted"},
            ),
        ),
    )
    model_ref = "cloud_0001/main"
    query = ProviderAvailabilityQuery(
        _Storage(connection),
        _Reports(()),
        serving_index=lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(
                CoreEndpointRoute(model_ref, ("food_common",), ("vision",)),
            ),
        ),
    )
    state = query._availability_for_channel(model_ref, "vision")

    assert state.status == "unknown"
    assert state.reason_code == "no_capability_evidence"
