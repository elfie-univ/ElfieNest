from datetime import datetime, timedelta, timezone

from app.features.configuration.food import StoredModelEvidence
from infrastructure.models.food_technology import _project_model
from infrastructure.models.provider_records import ProviderModelRecord as ExactModel
from infrastructure.models.report_records import ValidationObservation
from infrastructure.persistence.food_evidence import (
    _production_capability_observations,
    query_model_evidence,
    record_model_evidence,
)
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from infrastructure.persistence.reports.report_repository import ReportRepository

PROVIDER_CATALOG = load_provider_catalog()


def _configure_inventory(store: ProviderConnectionStore) -> None:
    store.replace(
        ProviderConnection(
            connection_id="ollama_0001",
            catalog_id="ollama",
            alias="Ollama",
            models=(
                ProviderModelRecord("local", supports_tools=True),
                ProviderModelRecord("hidden", hidden=True),
                ProviderModelRecord("unavailable", discovery_state="source_missing"),
                ProviderModelRecord("odd-id", display_name="GLM-5"),
            ),
        )
    )
    store.replace(
        ProviderConnection(
            connection_id="custom_openai_0001",
            catalog_id="custom_openai",
            alias="Archived",
            enabled=False,
            archived=True,
            models=(ProviderModelRecord("archived-model"),),
        )
    )


def _evidence(reference: str, verified: bool, observed_at: str) -> StoredModelEvidence:
    return StoredModelEvidence(
        reference=reference,
        display_name=reference,
        capabilities=frozenset({"text", "tools"}),
        verified=verified,
        observed_at=observed_at,
        tool_test_passed=verified,
    )


def test_projection_changes_from_never_to_passed_to_failed(tmp_path) -> None:
    provider_path = tmp_path / "providers.yaml"
    provider_store = ProviderConnectionStore(provider_path)
    repository = ReportRepository(tmp_path / "reports.db")
    _configure_inventory(provider_store)
    now = datetime.now(timezone.utc)

    initial = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now,
    )
    provider_bytes = provider_path.read_bytes()
    record_model_evidence(
        (_evidence("ollama_0001/local", True, now.isoformat()),),
        repository=repository,
        scope="test",
        trigger="benchmark",
    )
    passed = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now,
    )
    record_model_evidence(
        (
            _evidence(
                "ollama_0001/local",
                False,
                (now + timedelta(seconds=1)).isoformat(),
            ),
        ),
        repository=repository,
        scope="test",
        trigger="benchmark",
    )
    failed = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now + timedelta(seconds=1),
    )

    assert initial["ollama_0001/local"].status == "never_verified"
    assert passed["ollama_0001/local"].status == "verified"
    assert passed["ollama_0001/local"].fresh
    assert failed["ollama_0001/local"].status == "failed"
    assert not failed["ollama_0001/local"].verified
    assert provider_path.read_bytes() == provider_bytes


def test_projection_marks_stale_hidden_and_unavailable_as_ineligible(tmp_path) -> None:
    provider_store = ProviderConnectionStore(tmp_path / "providers.yaml")
    repository = ReportRepository(tmp_path / "reports.db")
    _configure_inventory(provider_store)
    now = datetime.now(timezone.utc)
    record_model_evidence(
        (
            _evidence(
                "ollama_0001/local",
                True,
                (now - timedelta(hours=25)).isoformat(),
            ),
        ),
        repository=repository,
        scope="test",
        trigger="benchmark",
    )

    evidence = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now,
    )

    assert evidence["ollama_0001/local"].status == "stale"
    assert not evidence["ollama_0001/local"].verified
    assert evidence["ollama_0001/hidden"].status == "hidden"
    assert evidence["ollama_0001/unavailable"].status == "unavailable"
    assert "custom_openai_0001/archived-model" not in evidence


def test_projection_uses_inventory_identity(tmp_path) -> None:
    provider_store = ProviderConnectionStore(tmp_path / "providers.yaml")
    repository = ReportRepository(tmp_path / "reports.db")
    _configure_inventory(provider_store)
    now = datetime.now(timezone.utc)
    record_model_evidence(
        (_evidence("ollama_0001/odd-id", True, now.isoformat()),),
        repository=repository,
        scope="test",
        trigger="benchmark",
    )

    evidence = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now,
    )

    assert evidence["ollama_0001/odd-id"].display_name == "GLM-5"


def test_projection_attaches_catalog_food_generation_preference(tmp_path) -> None:
    provider_store = ProviderConnectionStore(tmp_path / "providers.yaml")
    repository = ReportRepository(tmp_path / "reports.db")
    provider_store.replace(
        ProviderConnection(
            connection_id="ollama_0001",
            catalog_id="ollama",
            alias="Ollama",
            models=(ProviderModelRecord("qwen2.5:0.5b"),),
        )
    )
    now = datetime.now(timezone.utc)
    record_model_evidence(
        (_evidence("ollama_0001/qwen2.5:0.5b", True, now.isoformat()),),
        repository=repository,
        scope="test",
        trigger="benchmark",
    )

    evidence = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now,
    )["ollama_0001/qwen2.5:0.5b"]

    assert evidence.auto_selection_priority == 20
    assert evidence.quality_tier == 1


def test_capability_observations_overlay_model_health_without_replacing_it(
    tmp_path,
) -> None:
    provider_store = ProviderConnectionStore(tmp_path / "providers.yaml")
    repository = ReportRepository(tmp_path / "reports.db")
    _configure_inventory(provider_store)
    now = datetime.now(timezone.utc)
    reference = "ollama_0001/local"

    base_run = repository.start_run(scope=f"model:{reference}", trigger="full")
    repository.append_observation(
        run_id=base_run,
        subject_kind="model",
        subject_id=reference,
        observed_at=now.isoformat(),
        status="passed",
        details={
            "evidence_kind": "model_validation",
            "validation_mode": "full",
        },
    )
    repository.finish_run(base_run, status="complete")
    capability_run = repository.start_run(
        scope=f"model:{reference}:capability:tools",
        trigger="single",
    )
    repository.append_observation(
        run_id=capability_run,
        subject_kind="model",
        subject_id=reference,
        observed_at=(now + timedelta(seconds=1)).isoformat(),
        status="passed",
        details={
            "evidence_kind": "capability",
            "capability": "tools",
            "capability_state": "supported",
            "capability_evidence": "verified",
        },
    )
    repository.finish_run(capability_run, status="complete")

    evidence = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now + timedelta(seconds=1),
    )[reference]

    assert evidence.status == "verified"
    assert evidence.verified is True
    assert evidence.capability_states == {"tools": "supported"}
    assert "tools" in evidence.capabilities
    assert evidence.tool_test_passed is True


def test_unsupported_capability_does_not_make_text_health_disappear(tmp_path) -> None:
    provider_store = ProviderConnectionStore(tmp_path / "providers.yaml")
    repository = ReportRepository(tmp_path / "reports.db")
    _configure_inventory(provider_store)
    now = datetime.now(timezone.utc)
    reference = "ollama_0001/local"

    base_run = repository.start_run(scope=f"model:{reference}", trigger="full")
    repository.append_observation(
        run_id=base_run,
        subject_kind="model",
        subject_id=reference,
        observed_at=now.isoformat(),
        status="passed",
        details={"evidence_kind": "model_validation", "validation_mode": "full"},
    )
    repository.finish_run(base_run, status="complete")
    capability_run = repository.start_run(
        scope=f"model:{reference}:capability:vision",
        trigger="single",
    )
    repository.append_observation(
        run_id=capability_run,
        subject_kind="model",
        subject_id=reference,
        observed_at=(now + timedelta(seconds=1)).isoformat(),
        status="failed",
        details={
            "evidence_kind": "capability",
            "capability": "vision",
            "capability_state": "unsupported",
            "capability_evidence": "verified",
        },
    )
    repository.finish_run(capability_run, status="complete")

    evidence = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now + timedelta(seconds=1),
    )[reference]

    assert evidence.status == "verified"
    assert evidence.verified is True
    assert evidence.capability_states == {"vision": "unsupported"}


def test_latest_capability_observation_wins_over_older_observation(tmp_path) -> None:
    provider_store = ProviderConnectionStore(tmp_path / "providers.yaml")
    repository = ReportRepository(tmp_path / "reports.db")
    _configure_inventory(provider_store)
    now = datetime.now(timezone.utc)
    reference = "ollama_0001/local"

    base_run = repository.start_run(scope=f"model:{reference}", trigger="full")
    repository.append_observation(
        run_id=base_run,
        subject_kind="model",
        subject_id=reference,
        observed_at=now.isoformat(),
        status="passed",
        details={"evidence_kind": "model_validation", "validation_mode": "full"},
    )
    repository.finish_run(base_run, status="complete")

    capability_run = repository.start_run(
        scope=f"model:{reference}:capability:vision",
        trigger="single",
    )
    for observed_at, state in (
        (now + timedelta(seconds=1), "supported"),
        (now + timedelta(seconds=2), "unsupported"),
    ):
        repository.append_observation(
            run_id=capability_run,
            subject_kind="model",
            subject_id=reference,
            observed_at=observed_at.isoformat(),
            status="passed" if state == "supported" else "failed",
            details={
                "evidence_kind": "capability",
                "capability": "vision",
                "capability_state": state,
                "capability_evidence": "verified",
            },
        )
    repository.finish_run(capability_run, status="complete")

    evidence = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        repository=repository,
        connection_store=provider_store,
        now=now + timedelta(seconds=2),
    )[reference]

    assert evidence.status == "verified"
    assert evidence.capability_states == {"vision": "unsupported"}
    assert "vision" not in evidence.capabilities


def test_food_evidence_never_infers_capability_from_canonical_model_family() -> None:
    model = ExactModel("kimi-k2.6", display_name="Kimi K2.6")
    observation = ValidationObservation(
        observation_id=1,
        run_id="run-1",
        subject_kind="model",
        subject_id="provider_0001/kimi-k2.6",
        observed_at="2026-08-16T00:00:00+00:00",
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details={"capabilities": ["text"]},
    )

    projected = _project_model(
        "provider_0001/kimi-k2.6",
        model,
        observation,
        is_local=False,
        now=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )

    assert projected.capabilities == frozenset({"text"})


def test_food_evidence_does_not_trust_unscoped_capability_labels() -> None:
    model = ExactModel("unscoped")
    observation = ValidationObservation(
        observation_id=1,
        run_id="run-1",
        subject_kind="model",
        subject_id="provider_0001/unscoped",
        observed_at="2026-08-16T00:00:00+00:00",
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details={"capabilities": ["text", "vision", "tools"]},
    )

    projected = _project_model(
        "provider_0001/unscoped",
        model,
        observation,
        is_local=False,
        now=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )

    assert projected.capabilities == frozenset({"text"})
    assert projected.capability_states == {}


def test_food_evidence_does_not_promote_manual_capability_declaration() -> None:
    model = ExactModel(
        "manual-vision",
        source="manual",
        supports_vision=True,
        capability_evidence={"vision": "declared_by_user"},
    )
    observation = ValidationObservation(
        observation_id=1,
        run_id="run-1",
        subject_kind="model",
        subject_id="provider_0001/manual-vision",
        observed_at="2026-08-16T00:00:00+00:00",
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details={"capabilities": ["text"]},
    )

    projected = _project_model(
        "provider_0001/manual-vision",
        model,
        observation,
        is_local=False,
        now=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )

    assert "vision" not in projected.capabilities
    assert "vision" not in projected.capability_states


def test_food_evidence_does_not_promote_accepted_capability_probe() -> None:
    model = ExactModel(
        "accepted-vision",
        supports_vision=True,
        capability_evidence={"vision": "accepted"},
    )
    observation = ValidationObservation(
        observation_id=1,
        run_id="run-1",
        subject_kind="model",
        subject_id="provider_0001/accepted-vision",
        observed_at="2026-08-16T00:00:00+00:00",
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details={
            "evidence_kind": "capability",
            "capability": "vision",
            "capability_state": "supported",
            "capability_evidence": "accepted",
        },
    )

    projected = _project_model(
        "provider_0001/accepted-vision",
        model,
        None,
        is_local=False,
        now=datetime(2026, 8, 16, tzinfo=timezone.utc),
        capability_observations=(observation,),
    )

    assert "vision" not in projected.capabilities
    assert "vision" not in projected.capability_states


def test_production_tool_use_promotes_only_that_exact_capability() -> None:
    runtime = ValidationObservation(
        observation_id=1,
        run_id="runtime-1",
        subject_kind="model",
        subject_id="provider_0001/production",
        observed_at="2026-08-16T00:00:00+00:00",
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details={
            "event_type": "model_call",
            "workload_kind": "production",
            "tool_called": True,
        },
    )

    promoted = _production_capability_observations((runtime,))

    assert len(promoted) == 1
    assert promoted[0].details["capability"] == "tools"
    assert promoted[0].details["capability_evidence"] == "verified"


def test_connection_billing_block_overrides_fresh_model_evidence(tmp_path) -> None:
    provider_store = ProviderConnectionStore(tmp_path / "providers.yaml")
    _configure_inventory(provider_store)
    now = datetime(2026, 8, 16, tzinfo=timezone.utc)
    model_observation = ValidationObservation(
        observation_id=1,
        run_id="model-run",
        subject_kind="model",
        subject_id="ollama_0001/local",
        observed_at=now.isoformat(),
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details={"capabilities": ["text"]},
    )
    provider_observation = ValidationObservation(
        observation_id=2,
        run_id="provider-run",
        subject_kind="provider",
        subject_id="ollama_0001",
        observed_at=now.isoformat(),
        status="failed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category="billing",
        error_message="billing blocked",
        details={
            "error_code": "billing_blocked",
            "error_scope": "connection",
            "error_category": "billing",
        },
    )

    evidence = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        connection_store=provider_store,
        observations=(model_observation,),
        provider_observations=(provider_observation,),
        now=now,
    )

    projected = evidence["ollama_0001/local"]
    assert projected.status == "unavailable"
    assert not projected.verified
    assert not projected.fresh


def test_projection_rejects_model_evidence_from_old_configuration_fingerprint(
    tmp_path,
) -> None:
    provider_store = ProviderConnectionStore(tmp_path / "providers.yaml")
    provider_store.replace(
        ProviderConnection(
            connection_id="cloud_0001",
            catalog_id="custom_openai",
            alias="Cloud",
            credential_ref="CLOUD_KEY",
            models=(ProviderModelRecord("main"),),
        )
    )
    now = datetime(2026, 8, 16, tzinfo=timezone.utc)
    old = ValidationObservation(
        observation_id=1,
        run_id="old-run",
        subject_kind="model",
        subject_id="cloud_0001/main",
        observed_at=now.isoformat(),
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details={
            "config_fingerprint": "old-fingerprint",
            "evidence_source": "production",
        },
    )

    evidence = query_model_evidence(
        provider_catalog=PROVIDER_CATALOG,
        connection_store=provider_store,
        observations=(old,),
        secret_resolver=lambda _name: "current-secret",
        now=now,
    )

    assert evidence["cloud_0001/main"].status == "never_verified"
    assert evidence["cloud_0001/main"].fresh is False
