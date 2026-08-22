from __future__ import annotations

from datetime import datetime, timezone

from devtools.brain_eval.contracts import (
    DecisionStatus,
    DimensionEffect,
    GateViolation,
    JudgeCalibrationReport,
    PromotionPolicy,
    QualityDimension,
    ReliabilityComparison,
    ResourceBudget,
    ResourceCheck,
)
from devtools.brain_eval.promotion import decide_promotion


def _effect(
    dimension: QualityDimension,
    *,
    estimate: float = 0.10,
    lower: float = 0.05,
    upper: float = 0.15,
) -> DimensionEffect:
    return DimensionEffect(
        dimension=dimension,
        valid=True,
        net_advantage=estimate,
        lower_bound=lower,
        upper_bound=upper,
        pair_count=20,
        invalid_pair_count=0,
        scenario_family_count=4,
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
        minimum_scenario_families=3,
        consistency_k=3,
        resource_budget=ResourceBudget(
            max_mean_latency_ms=1000.0,
            max_p95_latency_ms=2000.0,
            max_mean_model_calls=3.0,
            max_mean_output_tokens=1000.0,
            max_mean_cost_microunits=10000.0,
        ),
        judge_calibration_required=True,
        minimum_calibration_anchors=6,
        maximum_calibration_tolerance=0.05,
        minimum_judge_position_consistency=0.95,
        hidden_confirmation_required=True,
        constitutional_anchor_required=True,
    )


def _protected_effects() -> tuple[DimensionEffect, ...]:
    return tuple(
        _effect(dimension, estimate=0.0, lower=-0.01, upper=0.01)
        for dimension in QualityDimension
        if dimension is not QualityDimension.MEMORY_RELATIONSHIPS
    )


def _calibration() -> JudgeCalibrationReport:
    return JudgeCalibrationReport(
        calibration_id="calibration-v1",
        protocol_version="0.1.0",
        judge_id="judge-a",
        judge_revision="judge-v1",
        rubric_versions=("q1-v1", "q2-v1", "q3-v1", "q4-v1", "q5-v1", "q6-v1"),
        anchor_set_revision="human-anchor-v1",
        anchor_set_sha256="c" * 64,
        calibrated_at=datetime.now(timezone.utc),
        dimensions_covered=tuple(QualityDimension),
        passed=True,
        judge_human_agreement=0.95,
        human_human_agreement=0.96,
        position_flip_consistency=0.99,
        anchor_coverage=1.0,
        anchor_count=20,
        matched_anchor_count=20,
        tolerance=0.05,
        minimum_position_consistency=0.95,
    )


def _reliability(
    *,
    baseline: float = 0.90,
    candidate: float = 0.90,
    baseline_consistency: float = 0.80,
    candidate_consistency: float = 0.80,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
    consistency_lower_bound: float | None = None,
    consistency_upper_bound: float | None = None,
) -> ReliabilityComparison:
    delta = candidate - baseline
    consistency_delta = candidate_consistency - baseline_consistency
    return ReliabilityComparison(
        valid=True,
        baseline_success_rate=baseline,
        candidate_success_rate=candidate,
        delta=delta,
        delta_lower_bound=(
            max(-1.0, delta - 0.01) if lower_bound is None else lower_bound
        ),
        delta_upper_bound=(
            min(1.0, delta + 0.01) if upper_bound is None else upper_bound
        ),
        baseline_consistency_at_k=baseline_consistency,
        candidate_consistency_at_k=candidate_consistency,
        consistency_delta=consistency_delta,
        consistency_delta_lower_bound=(
            max(-1.0, consistency_delta - 0.01)
            if consistency_lower_bound is None
            else consistency_lower_bound
        ),
        consistency_delta_upper_bound=(
            min(1.0, consistency_delta + 0.01)
            if consistency_upper_bound is None
            else consistency_upper_bound
        ),
        k=3,
        paired_episode_count=30,
        scenario_family_count=4,
        invalid_pair_count=0,
    )


def test_promote_requires_target_superiority_and_protected_noninferiority() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(
            candidate=0.92,
            candidate_consistency=0.82,
        ),
        resource_checks=(
            ResourceCheck(metric="mean_latency_ms", passed=True, detail="within"),
        ),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.PROMOTE
    assert decision.epi == 10.0


def test_positive_epi_cannot_compensate_for_p0() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(
            GateViolation(
                code="P0_FALSE_COMPLETION",
                scenario_family_id="p0-receipt-truth",
                message="claimed completion without receipt",
                evidence_ids=("claim-1",),
            ),
        ),
        missing_p0_families=(),
        reliability=_reliability(
            candidate=0.95,
            candidate_consistency=0.90,
        ),
        resource_checks=(),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.REJECT
    assert decision.epi is None
    assert "P0_FALSE_COMPLETION" in decision.reasons


def test_missing_p0_family_is_invalid_not_a_clean_gate_pass() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=("p0-private-disclosure",),
        reliability=_reliability(),
        resource_checks=(),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.INVALID
    assert "p0_family_not_evaluated:p0-private-disclosure" in decision.reasons


def test_insufficient_target_evidence_is_observe_not_promote() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(
                QualityDimension.MEMORY_RELATIONSHIPS,
                estimate=0.02,
                lower=-0.01,
                upper=0.05,
            ),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(),
        resource_checks=(),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.OBSERVE
    assert decision.epi == 2.0


def test_uncertain_protected_floor_observes_instead_of_claiming_regression() -> None:
    protected = list(_protected_effects())
    protected[0] = _effect(
        protected[0].dimension,
        estimate=-0.03,
        lower=-0.05,
        upper=-0.01,
    )

    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *protected,
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(),
        resource_checks=(),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.OBSERVE
    assert any(
        "protected_noninferiority_unproven" in reason for reason in decision.reasons
    )


def test_credible_protected_regression_rejects() -> None:
    protected = list(_protected_effects())
    protected[0] = _effect(
        protected[0].dimension,
        estimate=-0.05,
        lower=-0.07,
        upper=-0.03,
    )

    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *protected,
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(),
        resource_checks=(),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.REJECT
    assert any("protected_regression" in reason for reason in decision.reasons)


def test_uncertain_reliability_noninferiority_observes() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(lower_bound=-0.02, upper_bound=0.01),
        resource_checks=(),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.OBSERVE
    assert "reliability_noninferiority_unproven" in decision.reasons


def test_uncertain_consistency_noninferiority_observes() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(
            consistency_lower_bound=-0.02,
            consistency_upper_bound=0.01,
        ),
        resource_checks=(),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.OBSERVE
    assert "reliability_consistency_noninferiority_unproven" in decision.reasons


def test_credible_consistency_regression_rejects() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(
            baseline_consistency=0.90,
            candidate_consistency=0.80,
            consistency_lower_bound=-0.15,
            consistency_upper_bound=-0.05,
        ),
        resource_checks=(),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.REJECT
    assert "reliability_consistency_regression" in decision.reasons


def test_missing_resource_evidence_invalidates_instead_of_rejecting_candidate() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(),
        resource_checks=(
            ResourceCheck(
                metric="mean_output_tokens",
                valid=False,
                passed=False,
                detail="missing",
            ),
        ),
        judge_calibration=_calibration(),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.INVALID
    assert "resource_evidence_missing:mean_output_tokens" in decision.reasons


def test_missing_judge_calibration_makes_the_run_invalid() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(),
        resource_checks=(),
        judge_calibration=None,
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.INVALID
    assert "judge_calibration_not_run" in decision.reasons


def test_failed_judge_calibration_invalidates_the_measurement_not_candidate() -> None:
    decision = decide_promotion(
        policy=_policy(),
        effects=(
            _effect(QualityDimension.MEMORY_RELATIONSHIPS),
            *_protected_effects(),
        ),
        gate_violations=(),
        missing_p0_families=(),
        reliability=_reliability(),
        resource_checks=(),
        judge_calibration=_calibration().model_copy(update={"passed": False}),
        hidden_confirmation_passed=True,
        constitutional_anchor_passed=True,
    )

    assert decision.status is DecisionStatus.INVALID
    assert "judge_calibration_failed" in decision.reasons
