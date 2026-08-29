from __future__ import annotations

import pytest

from devtools.brain_eval.contracts import (
    EpisodeEvidence,
    ResourceBudget,
    ResourceObservation,
    ScenarioVerdict,
    ScenarioVerdictSource,
)
from devtools.brain_eval.evaluation import (
    check_resource_budget,
    compare_reliability,
)


def _episode(
    candidate_id: str,
    family_id: str,
    seed: int,
    *,
    success: bool,
    variant_id: str = "default",
    with_verdict: bool = True,
    latency_ms: float = 100.0,
    model_calls: int = 1,
    output_tokens: int | None = 20,
    cost_microunits: int | None = 100,
) -> EpisodeEvidence:
    return EpisodeEvidence(
        candidate_id=candidate_id,
        candidate_spec_sha256="d" * 64,
        scenario_family_id=family_id,
        scenario_version="1.0.0",
        variant_id=variant_id,
        fixture_id="anchor-elfie",
        seed=seed,
        execution_success=True,
        scenario_verdict=(
            ScenarioVerdict(
                source=ScenarioVerdictSource.DETERMINISTIC_ADAPTER,
                evaluator_id="test-scenario-adapter",
                evaluator_revision="v1",
                passed=success,
                evidence=(f"{family_id}:{seed}",),
            )
            if with_verdict
            else None
        ),
        hidden=False,
        resources=ResourceObservation(
            latency_ms=latency_ms,
            model_calls=model_calls,
            input_tokens=20,
            output_tokens=output_tokens,
            cost_microunits=cost_microunits,
        ),
    )


def test_reliability_is_paired_and_reports_consistency_at_k() -> None:
    baseline = (
        _episode("baseline", "family-a", 1, success=True),
        _episode("baseline", "family-a", 2, success=False),
        _episode("baseline", "family-b", 1, success=True),
        _episode("baseline", "family-b", 2, success=True),
    )
    candidate = (
        _episode("candidate", "family-a", 1, success=True),
        _episode("candidate", "family-a", 2, success=True),
        _episode("candidate", "family-b", 1, success=True),
        _episode("candidate", "family-b", 2, success=True),
    )

    comparison = compare_reliability(baseline, candidate, k=2)

    assert comparison.baseline_success_rate == 0.75
    assert comparison.candidate_success_rate == 1.0
    assert comparison.delta == 0.25
    assert comparison.baseline_consistency_at_k == 0.5
    assert comparison.candidate_consistency_at_k == 1.0
    assert comparison.consistency_delta == 0.5
    assert comparison.consistency_delta_lower_bound is not None
    assert comparison.consistency_delta_upper_bound is not None
    assert comparison.valid is True


def test_reliability_uses_all_repeats_instead_of_ignoring_late_failures() -> None:
    baseline = tuple(
        _episode("baseline", "family-a", seed, success=True) for seed in (1, 2, 3)
    )
    candidate = (
        _episode("candidate", "family-a", 1, success=True),
        _episode("candidate", "family-a", 2, success=True),
        _episode("candidate", "family-a", 3, success=False),
    )

    comparison = compare_reliability(baseline, candidate, k=2)

    assert comparison.baseline_consistency_at_k == 1.0
    assert comparison.candidate_consistency_at_k == pytest.approx(1 / 3)
    assert comparison.consistency_delta == pytest.approx(-2 / 3)


def test_execution_success_cannot_substitute_for_a_scenario_verdict() -> None:
    comparison = compare_reliability(
        (_episode("baseline", "family-a", 1, success=True),),
        (
            _episode(
                "candidate",
                "family-a",
                1,
                success=True,
                with_verdict=False,
            ),
        ),
        k=1,
    )

    assert comparison.valid is False
    assert comparison.invalid_reason == "scenario_verdict_missing"


def test_reliability_weights_scenario_families_not_variant_count() -> None:
    baseline = tuple(
        _episode(
            "baseline",
            "family-large",
            index,
            success=False,
            variant_id=f"variant-{index}",
        )
        for index in range(1, 10)
    ) + (_episode("baseline", "family-small", 1, success=True),)
    candidate = tuple(
        _episode(
            "candidate",
            "family-large",
            index,
            success=True,
            variant_id=f"variant-{index}",
        )
        for index in range(1, 10)
    ) + (_episode("candidate", "family-small", 1, success=False),)

    comparison = compare_reliability(baseline, candidate, k=1)

    assert comparison.delta == 0.0


def test_resource_budget_reports_missing_metrics_as_failure() -> None:
    candidate = (
        _episode(
            "candidate",
            "family-a",
            1,
            success=True,
            output_tokens=None,
            cost_microunits=None,
        ),
    )
    budget = ResourceBudget(
        max_mean_latency_ms=500.0,
        max_p95_latency_ms=800.0,
        max_mean_model_calls=2.0,
        max_mean_output_tokens=100.0,
        max_mean_cost_microunits=1000.0,
    )

    checks = check_resource_budget(candidate, budget)
    by_metric = {check.metric: check for check in checks}

    assert by_metric["mean_latency_ms"].passed is True
    assert by_metric["mean_output_tokens"].passed is False
    assert by_metric["mean_output_tokens"].valid is False
    assert by_metric["mean_cost_microunits"].passed is False
    assert "missing" in by_metric["mean_output_tokens"].detail
