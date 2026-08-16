from __future__ import annotations

from datetime import datetime, timezone

from infrastructure.models.report_records import ValidationObservation
from infrastructure.models.validation.provider_availability import (
    project_endpoint_availability,
    project_provider_status,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _observation(
    observation_id: int,
    observed_at: str,
    status: str,
    *,
    error_category: str | None = None,
    details: dict[str, object] | None = None,
) -> ValidationObservation:
    return ValidationObservation(
        observation_id=observation_id,
        run_id=f"run-{observation_id}",
        subject_kind="model",
        subject_id="connection/model",
        observed_at=observed_at,
        status=status,
        latency_ms=100.0,
        time_to_first_token_ms=None,
        error_category=error_category,
        error_message=None,
        details=details or {},
    )


def test_no_observation_is_unknown_without_network_access() -> None:
    snapshot = project_endpoint_availability("connection/model", (), now=NOW)

    assert snapshot.status == "unknown"
    assert snapshot.reason_code == "no_health_evidence"


def test_fresh_success_is_available_and_expires() -> None:
    snapshot = project_endpoint_availability(
        "connection/model",
        (_observation(1, "2026-08-15T11:00:00+00:00", "passed"),),
        now=NOW,
    )

    assert snapshot.status == "available"
    assert snapshot.reason_code == "fresh_success"
    assert snapshot.expires_at == "2026-08-16T11:00:00+00:00"


def test_one_transient_failure_degrades_but_three_failures_unavailable() -> None:
    one = project_endpoint_availability(
        "connection/model",
        (
            _observation(
                2,
                "2026-08-15T11:59:00+00:00",
                "failed",
                error_category="network",
            ),
            _observation(1, "2026-08-15T11:50:00+00:00", "passed"),
        ),
        now=NOW,
    )
    three = project_endpoint_availability(
        "connection/model",
        (
            _observation(
                4,
                "2026-08-15T11:59:00+00:00",
                "failed",
                error_category="network",
            ),
            _observation(
                3,
                "2026-08-15T11:58:00+00:00",
                "failed",
                error_category="network",
            ),
            _observation(
                2,
                "2026-08-15T11:57:00+00:00",
                "failed",
                error_category="network",
            ),
        ),
        now=NOW,
    )

    assert one.status == "degraded"
    assert three.status == "unavailable"
    assert three.reason_code == "transient_failure_threshold"


def test_account_block_and_request_error_have_different_scopes() -> None:
    blocked = project_endpoint_availability(
        "connection/model",
        (
            _observation(
                1,
                "2026-08-15T11:59:00+00:00",
                "failed",
                error_category="quota",
                details={"error_code": "billing_blocked"},
            ),
        ),
        now=NOW,
    )
    neutral = project_endpoint_availability(
        "connection/model",
        (
            _observation(
                2,
                "2026-08-15T11:59:00+00:00",
                "failed",
                details={"error_scope": "request", "error_code": "invalid_request"},
            ),
        ),
        now=NOW,
    )

    assert blocked.status == "unavailable"
    assert blocked.error_scope == "connection"
    assert neutral.status == "unknown"


def test_provider_aggregation_uses_serving_scope_when_supplied() -> None:
    first = project_endpoint_availability(
        "connection/primary",
        (_observation(1, "2026-08-15T11:00:00+00:00", "passed"),),
        now=NOW,
    )
    second = project_endpoint_availability(
        "connection/unused",
        (
            _observation(
                2,
                "2026-08-15T11:59:00+00:00",
                "failed",
                error_category="network",
            ),
        ),
        now=NOW,
    )

    assert (
        project_provider_status(
            (first, second), serving_subject_ids=("connection/primary",)
        )
        == "healthy"
    )
