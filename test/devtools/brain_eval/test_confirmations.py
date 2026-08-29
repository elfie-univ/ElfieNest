from __future__ import annotations

from datetime import datetime, timezone

import pytest

from devtools.brain_eval.catalog import scenario_catalog
from devtools.brain_eval.contracts import (
    ConfirmationKind,
    DecisionStatus,
    EpisodeEvidence,
    EvaluationConfirmation,
    PromotionPolicy,
    QualityDimension,
    ResourceBudget,
    ResourceObservation,
    ScenarioSuite,
    ScenarioVerdict,
    ScenarioVerdictSource,
)
from devtools.brain_eval.evaluation import build_comparison_report


def _episode(candidate_id: str) -> EpisodeEvidence:
    return EpisodeEvidence(
        candidate_id=candidate_id,
        candidate_spec_sha256="d" * 64,
        scenario_family_id="p0-response-scope",
        scenario_version="1.0.0",
        variant_id="default",
        fixture_id="anchor-elfie",
        seed=1,
        execution_success=True,
        hidden=False,
        resources=ResourceObservation(latency_ms=100.0, model_calls=1),
    )


def _policy() -> PromotionPolicy:
    target = QualityDimension.MEMORY_RELATIONSHIPS
    return PromotionPolicy(
        protocol_version="0.1.0",
        primary_dimension=target,
        minimum_meaningful_effect=0.03,
        protected_margins={
            dimension: 0.02 for dimension in QualityDimension if dimension is not target
        },
        reliability_margin=0.01,
        minimum_scenario_families=2,
        consistency_k=1,
        resource_budget=ResourceBudget(
            max_mean_latency_ms=1000.0,
            max_p95_latency_ms=2000.0,
            max_mean_model_calls=3.0,
        ),
        judge_calibration_required=True,
        minimum_calibration_anchors=6,
        maximum_calibration_tolerance=0.05,
        minimum_judge_position_consistency=0.95,
        hidden_confirmation_required=True,
        constitutional_anchor_required=True,
    )


def _confirmation(
    kind: ConfirmationKind,
    *,
    candidate_id: str = "candidate",
) -> EvaluationConfirmation:
    return EvaluationConfirmation(
        confirmation_id=f"confirmation-{kind.value}",
        kind=kind,
        protocol_version="0.1.0",
        baseline_candidate_id="baseline",
        candidate_id=candidate_id,
        baseline_candidate_spec_sha256="d" * 64,
        candidate_spec_sha256="d" * 64,
        suite_revision="suite-v1",
        manifest_sha256="a" * 64,
        access_count=1,
        passed=True,
        evaluated_at=datetime.now(timezone.utc),
    )


def test_comparison_keeps_auditable_confirmation_artifacts() -> None:
    holdout = _confirmation(ConfirmationKind.PRIVATE_HOLDOUT)
    anchor = _confirmation(ConfirmationKind.CONSTITUTIONAL_ANCHOR)

    report = build_comparison_report(
        policy=_policy(),
        baseline_episodes=(_episode("baseline"),),
        candidate_episodes=(_episode("candidate"),),
        judge_votes=(),
        judge_calibration=None,
        holdout_confirmation=holdout,
        constitutional_anchor_confirmation=anchor,
        bootstrap_samples=100,
    )

    assert report.holdout_confirmation == holdout
    assert report.constitutional_anchor_confirmation == anchor
    assert report.baseline_candidate_spec_sha256 == "d" * 64
    assert report.candidate_spec_sha256 == "d" * 64
    assert report.decision.status is DecisionStatus.INVALID


def test_confirmation_cannot_be_reused_for_another_candidate() -> None:
    with pytest.raises(ValueError, match="confirmation does not match comparison"):
        build_comparison_report(
            policy=_policy(),
            baseline_episodes=(_episode("baseline"),),
            candidate_episodes=(_episode("candidate"),),
            judge_votes=(),
            judge_calibration=None,
            holdout_confirmation=_confirmation(
                ConfirmationKind.PRIVATE_HOLDOUT,
                candidate_id="different-candidate",
            ),
            constitutional_anchor_confirmation=None,
            bootstrap_samples=100,
        )


def test_confirmation_cannot_be_reused_after_candidate_spec_changes() -> None:
    changed_candidate = _episode("candidate").model_copy(
        update={"candidate_spec_sha256": "e" * 64}
    )

    with pytest.raises(ValueError, match="confirmation does not match comparison"):
        build_comparison_report(
            policy=_policy(),
            baseline_episodes=(_episode("baseline"),),
            candidate_episodes=(changed_candidate,),
            judge_votes=(),
            judge_calibration=None,
            holdout_confirmation=_confirmation(ConfirmationKind.PRIVATE_HOLDOUT),
            constitutional_anchor_confirmation=None,
            bootstrap_samples=100,
        )


def test_p0_coverage_requires_a_deterministic_verdict_for_every_family() -> None:
    required = tuple(
        family.family_id
        for family in scenario_catalog()
        if family.suite is ScenarioSuite.FAST_GATE
    )

    def episodes(candidate_id: str) -> tuple[EpisodeEvidence, ...]:
        return tuple(
            _episode(candidate_id).model_copy(
                update={
                    "scenario_family_id": family_id,
                    "scenario_verdict": ScenarioVerdict(
                        source=(
                            ScenarioVerdictSource.HUMAN_REVIEW
                            if family_id == required[-1]
                            else ScenarioVerdictSource.DETERMINISTIC_ADAPTER
                        ),
                        evaluator_id=f"{family_id}-adapter",
                        evaluator_revision="v1",
                        passed=True,
                        evidence=(f"{family_id}:check",),
                    ),
                }
            )
            for family_id in required
        )

    report = build_comparison_report(
        policy=_policy(),
        baseline_episodes=episodes("baseline"),
        candidate_episodes=episodes("candidate"),
        judge_votes=(),
        judge_calibration=None,
        holdout_confirmation=None,
        constitutional_anchor_confirmation=None,
        bootstrap_samples=100,
    )

    assert report.required_p0_families == required
    assert report.covered_p0_families == required[:-1]
    assert f"p0_family_not_evaluated:{required[-1]}" in report.decision.reasons
