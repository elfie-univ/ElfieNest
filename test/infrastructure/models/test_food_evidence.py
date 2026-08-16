from datetime import datetime, timedelta, timezone

from app.features.configuration.food import StoredModelEvidence
from infrastructure.persistence.food_evidence import (
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
