"""Constrained promotion decision; EPI never overrides constitutional gates."""

from __future__ import annotations

from typing import Iterable, List, Mapping, Optional

from devtools.brain_eval.contracts import (
    DecisionStatus,
    DimensionEffect,
    GateViolation,
    JudgeCalibrationReport,
    PromotionDecision,
    PromotionPolicy,
    QualityDimension,
    ReliabilityComparison,
    ResourceCheck,
)


def decide_promotion(
    *,
    policy: PromotionPolicy,
    effects: Iterable[DimensionEffect],
    gate_violations: Iterable[GateViolation],
    missing_p0_families: Iterable[str],
    reliability: ReliabilityComparison,
    resource_checks: Iterable[ResourceCheck],
    judge_calibration: Optional[JudgeCalibrationReport],
    hidden_confirmation_passed: Optional[bool],
    constitutional_anchor_passed: Optional[bool],
) -> PromotionDecision:
    """Return PROMOTE/OBSERVE/REJECT/INVALID from a frozen experiment policy."""

    effect_by_dimension: Mapping[QualityDimension, DimensionEffect] = {
        effect.dimension: effect for effect in effects
    }
    gates = tuple(gate_violations)
    missing_p0 = tuple(sorted(set(missing_p0_families)))
    checks = tuple(resource_checks)
    target = effect_by_dimension.get(policy.primary_dimension)

    if gates:
        return PromotionDecision(
            status=DecisionStatus.REJECT,
            epi=None,
            primary_dimension=policy.primary_dimension,
            protected_floor=None,
            reasons=tuple(dict.fromkeys(item.code for item in gates)),
        )

    invalid_reasons: List[str] = []
    invalid_reasons.extend(
        f"p0_family_not_evaluated:{family_id}" for family_id in missing_p0
    )
    if target is None or not target.valid:
        invalid_reasons.append("target_effect_invalid")
    elif target.scenario_family_count < policy.minimum_scenario_families:
        invalid_reasons.append("target_family_coverage_insufficient")

    protected: List[DimensionEffect] = []
    for dimension in policy.protected_margins:
        effect = effect_by_dimension.get(dimension)
        if effect is None or not effect.valid:
            invalid_reasons.append(f"protected_effect_invalid:{dimension.value}")
        elif effect.scenario_family_count < policy.minimum_scenario_families:
            invalid_reasons.append(
                f"protected_family_coverage_insufficient:{dimension.value}"
            )
        else:
            protected.append(effect)

    if not reliability.valid:
        invalid_reasons.append(
            f"reliability_invalid:{reliability.invalid_reason or 'unknown'}"
        )
    elif reliability.scenario_family_count < policy.minimum_scenario_families:
        invalid_reasons.append("reliability_family_coverage_insufficient")
    invalid_reasons.extend(
        f"resource_evidence_missing:{check.metric}"
        for check in checks
        if not check.valid
    )

    if policy.hidden_confirmation_required and hidden_confirmation_passed is None:
        invalid_reasons.append("hidden_confirmation_not_run")
    if policy.judge_calibration_required and judge_calibration is None:
        invalid_reasons.append("judge_calibration_not_run")
    elif policy.judge_calibration_required and judge_calibration is not None:
        if judge_calibration.protocol_version != policy.protocol_version:
            invalid_reasons.append("judge_calibration_protocol_mismatch")
        if set(judge_calibration.dimensions_covered) != set(QualityDimension):
            invalid_reasons.append("judge_calibration_dimension_coverage_incomplete")
        if judge_calibration.anchor_count < policy.minimum_calibration_anchors:
            invalid_reasons.append("judge_calibration_anchor_coverage_insufficient")
        if judge_calibration.anchor_coverage < 1.0:
            invalid_reasons.append("judge_calibration_anchor_matching_incomplete")
        if judge_calibration.tolerance > policy.maximum_calibration_tolerance:
            invalid_reasons.append("judge_calibration_tolerance_too_loose")
        if (
            judge_calibration.minimum_position_consistency
            < policy.minimum_judge_position_consistency
            or judge_calibration.position_flip_consistency
            < policy.minimum_judge_position_consistency
        ):
            invalid_reasons.append(
                "judge_calibration_position_consistency_insufficient"
            )
        if not judge_calibration.passed:
            invalid_reasons.append("judge_calibration_failed")
    if policy.constitutional_anchor_required and constitutional_anchor_passed is None:
        invalid_reasons.append("constitutional_anchor_not_run")
    if invalid_reasons:
        return PromotionDecision(
            status=DecisionStatus.INVALID,
            epi=None,
            primary_dimension=policy.primary_dimension,
            protected_floor=None,
            reasons=tuple(invalid_reasons),
        )

    assert target is not None and target.net_advantage is not None
    assert target.lower_bound is not None
    epi = round(target.net_advantage * 100.0, 4)
    protected_floor = min(
        effect.lower_bound for effect in protected if effect.lower_bound is not None
    )

    reject_reasons: List[str] = []
    for effect in protected:
        margin = policy.protected_margins[effect.dimension]
        assert effect.lower_bound is not None
        assert effect.upper_bound is not None
        if effect.upper_bound < -margin:
            reject_reasons.append(f"protected_regression:{effect.dimension.value}")
    assert reliability.delta_lower_bound is not None
    assert reliability.delta_upper_bound is not None
    if reliability.delta_upper_bound < -policy.reliability_margin:
        reject_reasons.append("reliability_regression")
    assert reliability.consistency_delta_lower_bound is not None
    assert reliability.consistency_delta_upper_bound is not None
    if reliability.consistency_delta_upper_bound < -policy.reliability_margin:
        reject_reasons.append("reliability_consistency_regression")
    reject_reasons.extend(
        f"resource_budget:{check.metric}"
        for check in checks
        if check.valid and not check.passed
    )
    if policy.hidden_confirmation_required and hidden_confirmation_passed is False:
        reject_reasons.append("hidden_confirmation_failed")
    if policy.constitutional_anchor_required and constitutional_anchor_passed is False:
        reject_reasons.append("constitutional_anchor_failed")
    if reject_reasons:
        return PromotionDecision(
            status=DecisionStatus.REJECT,
            epi=epi,
            primary_dimension=policy.primary_dimension,
            protected_floor=protected_floor,
            reasons=tuple(reject_reasons),
        )

    observe_reasons = [
        f"protected_noninferiority_unproven:{effect.dimension.value}"
        for effect in protected
        if effect.lower_bound is not None
        and effect.lower_bound < -policy.protected_margins[effect.dimension]
    ]
    if reliability.delta_lower_bound < -policy.reliability_margin:
        observe_reasons.append("reliability_noninferiority_unproven")
    if reliability.consistency_delta_lower_bound < -policy.reliability_margin:
        observe_reasons.append("reliability_consistency_noninferiority_unproven")
    if target.lower_bound < policy.minimum_meaningful_effect:
        observe_reasons.append("target_evidence_below_meaningful_effect")
    if observe_reasons:
        return PromotionDecision(
            status=DecisionStatus.OBSERVE,
            epi=epi,
            primary_dimension=policy.primary_dimension,
            protected_floor=protected_floor,
            reasons=tuple(observe_reasons),
        )
    return PromotionDecision(
        status=DecisionStatus.PROMOTE,
        epi=epi,
        primary_dimension=policy.primary_dimension,
        protected_floor=protected_floor,
        reasons=("promotion_requirements_satisfied",),
    )


__all__ = ("decide_promotion",)
