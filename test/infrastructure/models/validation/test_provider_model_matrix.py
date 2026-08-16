from __future__ import annotations

from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.report_records import ValidationObservation
from infrastructure.models.validation.provider_model_matrix import build_model_matrix


def test_matrix_keeps_capability_probe_out_of_text_health_cell() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://gateway.example/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        models=(ProviderModelRecord("model-a"),),
    )
    observations = (
        ValidationObservation(
            observation_id=1,
            run_id="run-text",
            subject_kind="model",
            subject_id="cloud_0001/model-a",
            observed_at="2026-08-16T01:00:00+00:00",
            status="passed",
            latency_ms=120.0,
            time_to_first_token_ms=None,
            error_category=None,
            error_message=None,
            details={"validation_mode": "full", "evidence_source": "validation"},
        ),
        ValidationObservation(
            observation_id=2,
            run_id="run-capability",
            subject_kind="model",
            subject_id="cloud_0001/model-a",
            observed_at="2026-08-16T01:01:00+00:00",
            status="passed",
            latency_ms=8.0,
            time_to_first_token_ms=None,
            error_category=None,
            error_message=None,
            details={
                "evidence_kind": "capability",
                "capability": "vision",
                "capability_state": "supported",
                "capability_evidence": "verified",
            },
        ),
    )

    result = build_model_matrix(
        {connection.connection_id: connection},
        observations=observations,
        snapshot={"mode": "run", "run_id": "run-text"},
    )

    cell = result["models"][0]["connections"][0]
    assert cell["verification_status"] == "passed"
    assert cell["latency_ms"] == 120.0
    assert cell["capability_facts"][1] == {
        "name": "vision",
        "state": "supported",
        "evidence": "verified",
    }


def test_matrix_excludes_source_missing_models_from_normal_inventory() -> None:
    connection = ProviderConnection(
        connection_id="cloud_0001",
        catalog_id="custom_openai",
        alias="Cloud",
        api_base="https://gateway.example/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        models=(
            ProviderModelRecord("current"),
            ProviderModelRecord("old", discovery_state="source_missing"),
        ),
    )

    result = build_model_matrix({connection.connection_id: connection})

    assert [
        cell["model_id"]
        for model in result["models"]
        for cell in model["connections"]
        if cell["model_id"] is not None
    ] == ["current"]
