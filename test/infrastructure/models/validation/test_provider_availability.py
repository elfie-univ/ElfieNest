from __future__ import annotations

from datetime import datetime, timezone

from infrastructure.models.report_records import ValidationObservation
from infrastructure.models.validation.provider_availability import (
    REACHABILITY_FRESHNESS,
    project_capability_availability,
    project_endpoint_availability,
    project_provider_status,
    project_reachability,
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
    assert three.expires_at == "2026-08-15T12:09:00+00:00"


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


def test_reachability_is_separate_and_expires_after_five_minutes() -> None:
    observation = _observation(
        1,
        "2026-08-15T11:57:00+00:00",
        "passed",
        details={"evidence_kind": "reachability", "evidence_source": "heartbeat"},
    )

    fresh = project_reachability("connection", (observation,), now=NOW)
    stale = project_reachability(
        "connection",
        (observation,),
        now=datetime(2026, 8, 15, 12, 2, tzinfo=timezone.utc),
    )

    assert fresh.status == "available"
    assert (
        fresh.expires_at
        == (
            datetime.fromisoformat(observation.observed_at) + REACHABILITY_FRESHNESS
        ).isoformat()
    )
    assert stale.status == "unknown"
    assert stale.reason_code == "reachability_expired"


def test_reachability_requires_three_recent_transient_failures_before_unavailable() -> (
    None
):
    observations = tuple(
        _observation(
            observation_id,
            f"2026-08-15T11:{59 - index:02d}:00+00:00",
            "failed",
            error_category="network",
            details={"evidence_kind": "reachability"},
        )
        for index, observation_id in enumerate((3, 2, 1))
    )

    projection = project_reachability("connection", observations, now=NOW)

    assert projection.status == "unavailable"
    assert projection.reason_code == "transient_failure_threshold"
    assert projection.expires_at == "2026-08-15T12:09:00+00:00"


def test_untagged_provider_validation_is_not_reachability() -> None:
    projection = project_reachability(
        "connection",
        (_observation(1, "2026-08-15T11:59:00+00:00", "passed"),),
        now=NOW,
    )

    assert projection.status == "unknown"
    assert projection.reason_code == "no_reachability_evidence"


def test_capability_observation_does_not_change_text_health() -> None:
    observation = _observation(
        1,
        "2026-08-15T11:59:00+00:00",
        "passed",
        details={
            "validation_mode": "capability",
            "evidence_source": "capability_probe",
        },
    )

    snapshot = project_endpoint_availability(
        "connection/model",
        (observation,),
        now=NOW,
    )

    assert snapshot.status == "unknown"


def test_capability_account_block_is_connection_scoped_and_non_retryable() -> None:
    observation = _observation(
        1,
        "2026-08-15T11:59:00+00:00",
        "failed",
        error_category="billing",
        details={
            "evidence_kind": "capability",
            "capability": "vision",
            "error_code": "billing_blocked",
        },
    )

    snapshot = project_capability_availability(
        "connection/model",
        "vision",
        (observation,),
        now=NOW,
    )

    assert snapshot.status == "unavailable"
    assert snapshot.reason_code == "billing_blocked"
    assert snapshot.error_scope == "connection"
