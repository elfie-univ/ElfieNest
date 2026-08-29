"""Assemble paired evidence, statistics, resource checks and promotion."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from math import comb
from statistics import fmean
from typing import DefaultDict, Iterable, List, Mapping, Optional, Sequence, Tuple

from devtools.brain_eval.catalog import scenario_catalog
from devtools.brain_eval.contracts import (
    ComparisonReport,
    ConfirmationKind,
    EpisodeEvidence,
    EvaluationConfirmation,
    JudgeCalibrationReport,
    JudgeVote,
    PairwiseOutcome,
    PromotionPolicy,
    QualityDimension,
    ReliabilityComparison,
    ResourceBudget,
    ResourceCheck,
    ScenarioSuite,
    ScenarioVerdictSource,
)
from devtools.brain_eval.gates import evaluate_p0_gates
from devtools.brain_eval.judge import consolidate_position_flips
from devtools.brain_eval.promotion import decide_promotion
from devtools.brain_eval.statistics import estimate_dimension_effect


def compare_reliability(
    baseline_episodes: Iterable[EpisodeEvidence],
    candidate_episodes: Iterable[EpisodeEvidence],
    *,
    k: int,
    bootstrap_samples: int = 2000,
    random_seed: int = 0,
) -> ReliabilityComparison:
    """Compare success and all-k consistency on exactly paired episodes."""

    if k < 1:
        raise ValueError("k must be positive")
    if bootstrap_samples < 100:
        raise ValueError("bootstrap_samples must be at least 100")
    baseline = _episode_map(baseline_episodes, "baseline")
    candidate = _episode_map(candidate_episodes, "candidate")
    if set(baseline) != set(candidate):
        missing_candidate = sorted(set(baseline) - set(candidate))
        missing_baseline = sorted(set(candidate) - set(baseline))
        raise ValueError(
            "episode pairing mismatch: "
            f"missing_candidate={missing_candidate}, missing_baseline={missing_baseline}"
        )
    if not baseline:
        raise ValueError("at least one paired episode is required")

    ordered_keys = sorted(baseline)
    for key in ordered_keys:
        baseline_episode = baseline[key]
        candidate_episode = candidate[key]
        if (
            baseline_episode.scenario_version != candidate_episode.scenario_version
            or baseline_episode.hidden != candidate_episode.hidden
        ):
            raise ValueError(f"episode protocol mismatch for paired key: {key}")
    missing_verdicts = [
        key
        for key in ordered_keys
        if baseline[key].scenario_verdict is None
        or candidate[key].scenario_verdict is None
    ]
    family_count = len({key[0] for key in ordered_keys})
    if missing_verdicts:
        return ReliabilityComparison(
            valid=False,
            k=k,
            paired_episode_count=len(ordered_keys),
            scenario_family_count=family_count,
            invalid_pair_count=len(missing_verdicts),
            invalid_reason="scenario_verdict_missing",
        )

    for key in ordered_keys:
        baseline_verdict = baseline[key].scenario_verdict
        candidate_verdict = candidate[key].scenario_verdict
        assert baseline_verdict is not None and candidate_verdict is not None
        baseline_evaluator = (
            baseline_verdict.source,
            baseline_verdict.evaluator_id,
            baseline_verdict.evaluator_revision,
        )
        candidate_evaluator = (
            candidate_verdict.source,
            candidate_verdict.evaluator_id,
            candidate_verdict.evaluator_revision,
        )
        if baseline_evaluator != candidate_evaluator:
            raise ValueError(
                f"scenario verdict evaluator mismatch for paired key: {key}"
            )

    baseline_values = {
        key: bool(baseline[key].scenario_verdict.passed)  # type: ignore[union-attr]
        for key in ordered_keys
    }
    candidate_values = {
        key: bool(candidate[key].scenario_verdict.passed)  # type: ignore[union-attr]
        for key in ordered_keys
    }
    baseline_consistency_by_family = _family_consistency_at_k(
        baseline,
        baseline_values,
        k,
    )
    candidate_consistency_by_family = _family_consistency_at_k(
        candidate,
        candidate_values,
        k,
    )
    if (
        baseline_consistency_by_family is None
        or candidate_consistency_by_family is None
    ):
        return ReliabilityComparison(
            valid=False,
            k=k,
            paired_episode_count=len(ordered_keys),
            scenario_family_count=family_count,
            invalid_pair_count=0,
            invalid_reason="reliability_repeat_coverage_insufficient",
        )
    baseline_consistency = float(fmean(baseline_consistency_by_family.values()))
    candidate_consistency = float(fmean(candidate_consistency_by_family.values()))
    consistency_delta = candidate_consistency - baseline_consistency
    consistency_family_deltas = {
        family_id: candidate_consistency_by_family[family_id]
        - baseline_consistency_by_family[family_id]
        for family_id in baseline_consistency_by_family
    }
    consistency_lower, consistency_upper = _clustered_family_mean_interval(
        consistency_family_deltas,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed + 1,
    )
    consistency_lower = min(consistency_lower, consistency_delta)
    consistency_upper = max(consistency_upper, consistency_delta)
    baseline_rate = _family_weighted_success_rate(ordered_keys, baseline_values)
    candidate_rate = _family_weighted_success_rate(ordered_keys, candidate_values)
    delta = candidate_rate - baseline_rate
    lower, upper = _clustered_reliability_interval(
        ordered_keys,
        baseline_values,
        candidate_values,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
    )
    lower = min(lower, delta)
    upper = max(upper, delta)
    return ReliabilityComparison(
        valid=True,
        baseline_success_rate=baseline_rate,
        candidate_success_rate=candidate_rate,
        delta=delta,
        delta_lower_bound=lower,
        delta_upper_bound=upper,
        baseline_consistency_at_k=baseline_consistency,
        candidate_consistency_at_k=candidate_consistency,
        consistency_delta=consistency_delta,
        consistency_delta_lower_bound=consistency_lower,
        consistency_delta_upper_bound=consistency_upper,
        k=k,
        paired_episode_count=len(ordered_keys),
        scenario_family_count=family_count,
        invalid_pair_count=0,
    )


def check_resource_budget(
    episodes: Iterable[EpisodeEvidence],
    budget: ResourceBudget,
) -> tuple[ResourceCheck, ...]:
    """Check absolute candidate resources without folding them into EPI."""

    selected = tuple(episodes)
    if not selected:
        raise ValueError("resource checks require at least one episode")
    latencies = [episode.resources.latency_ms for episode in selected]
    model_calls = [float(episode.resources.model_calls) for episode in selected]
    checks: List[ResourceCheck] = [
        _bounded_check(
            "mean_latency_ms",
            float(fmean(latencies)),
            budget.max_mean_latency_ms,
        ),
        _bounded_check(
            "p95_latency_ms",
            _quantile(sorted(latencies), 0.95),
            budget.max_p95_latency_ms,
        ),
        _bounded_check(
            "mean_model_calls",
            float(fmean(model_calls)),
            budget.max_mean_model_calls,
        ),
    ]
    if budget.max_mean_output_tokens is not None:
        checks.append(
            _optional_mean_check(
                "mean_output_tokens",
                [episode.resources.output_tokens for episode in selected],
                budget.max_mean_output_tokens,
            )
        )
    if budget.max_mean_cost_microunits is not None:
        checks.append(
            _optional_mean_check(
                "mean_cost_microunits",
                [episode.resources.cost_microunits for episode in selected],
                budget.max_mean_cost_microunits,
            )
        )
    return tuple(checks)


def build_comparison_report(
    *,
    policy: PromotionPolicy,
    baseline_episodes: Iterable[EpisodeEvidence],
    candidate_episodes: Iterable[EpisodeEvidence],
    judge_votes: Iterable[JudgeVote],
    judge_calibration: Optional[JudgeCalibrationReport],
    holdout_confirmation: Optional[EvaluationConfirmation],
    constitutional_anchor_confirmation: Optional[EvaluationConfirmation],
    bootstrap_samples: int = 2000,
    random_seed: int = 0,
) -> ComparisonReport:
    """Build one complete comparison from frozen artifacts."""

    baseline = tuple(baseline_episodes)
    candidate = tuple(candidate_episodes)
    baseline_id = _single_candidate_id(baseline, "baseline")
    candidate_id = _single_candidate_id(candidate, "candidate")
    baseline_spec_sha256 = _single_candidate_spec_sha256(baseline, "baseline")
    candidate_spec_sha256 = _single_candidate_spec_sha256(candidate, "candidate")
    _validate_confirmation(
        holdout_confirmation,
        expected_kind=ConfirmationKind.PRIVATE_HOLDOUT,
        protocol_version=policy.protocol_version,
        baseline_candidate_id=baseline_id,
        candidate_id=candidate_id,
        baseline_candidate_spec_sha256=baseline_spec_sha256,
        candidate_spec_sha256=candidate_spec_sha256,
    )
    _validate_confirmation(
        constitutional_anchor_confirmation,
        expected_kind=ConfirmationKind.CONSTITUTIONAL_ANCHOR,
        protocol_version=policy.protocol_version,
        baseline_candidate_id=baseline_id,
        candidate_id=candidate_id,
        baseline_candidate_spec_sha256=baseline_spec_sha256,
        candidate_spec_sha256=candidate_spec_sha256,
    )
    if baseline_id == candidate_id:
        raise ValueError(
            "baseline and candidate must have different candidate_id values"
        )
    selected_votes = tuple(judge_votes)
    _validate_judge_calibration_identity(selected_votes, judge_calibration)
    reliability = compare_reliability(
        baseline,
        candidate,
        k=policy.consistency_k,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed + 10_000,
    )
    outcomes = consolidate_position_flips(selected_votes)
    _validate_judge_coverage(baseline, outcomes)
    effects = tuple(
        estimate_dimension_effect(
            outcomes,
            dimension,
            bootstrap_samples=bootstrap_samples,
            random_seed=random_seed + index,
        )
        for index, dimension in enumerate(QualityDimension)
    )
    required_p0_families = tuple(
        family.family_id
        for family in scenario_catalog()
        if family.suite is ScenarioSuite.FAST_GATE
    )
    covered_p0_families = tuple(
        family_id
        for family_id in required_p0_families
        if _p0_family_has_deterministic_coverage(candidate, family_id)
    )
    missing_p0_families = tuple(
        family_id
        for family_id in required_p0_families
        if family_id not in covered_p0_families
    )
    gate_violations = evaluate_p0_gates(candidate)
    resource_checks = check_resource_budget(candidate, policy.resource_budget)
    decision = decide_promotion(
        policy=policy,
        effects=effects,
        gate_violations=gate_violations,
        missing_p0_families=missing_p0_families,
        reliability=reliability,
        resource_checks=resource_checks,
        judge_calibration=judge_calibration,
        hidden_confirmation_passed=(
            holdout_confirmation.passed if holdout_confirmation is not None else None
        ),
        constitutional_anchor_passed=(
            constitutional_anchor_confirmation.passed
            if constitutional_anchor_confirmation is not None
            else None
        ),
    )
    return ComparisonReport(
        protocol_version=policy.protocol_version,
        baseline_candidate_id=baseline_id,
        candidate_id=candidate_id,
        baseline_candidate_spec_sha256=baseline_spec_sha256,
        candidate_spec_sha256=candidate_spec_sha256,
        required_p0_families=required_p0_families,
        covered_p0_families=covered_p0_families,
        effects=effects,
        gate_violations=gate_violations,
        reliability=reliability,
        resource_checks=resource_checks,
        judge_calibration=judge_calibration,
        holdout_confirmation=holdout_confirmation,
        constitutional_anchor_confirmation=constitutional_anchor_confirmation,
        decision=decision,
    )


def _validate_confirmation(
    confirmation: Optional[EvaluationConfirmation],
    *,
    expected_kind: ConfirmationKind,
    protocol_version: str,
    baseline_candidate_id: str,
    candidate_id: str,
    baseline_candidate_spec_sha256: str,
    candidate_spec_sha256: str,
) -> None:
    if confirmation is None:
        return
    expected = (
        expected_kind,
        protocol_version,
        baseline_candidate_id,
        candidate_id,
        baseline_candidate_spec_sha256,
        candidate_spec_sha256,
    )
    actual = (
        confirmation.kind,
        confirmation.protocol_version,
        confirmation.baseline_candidate_id,
        confirmation.candidate_id,
        confirmation.baseline_candidate_spec_sha256,
        confirmation.candidate_spec_sha256,
    )
    if actual != expected:
        raise ValueError(
            "confirmation does not match comparison: "
            f"expected={expected}, actual={actual}"
        )


def _p0_family_has_deterministic_coverage(
    episodes: Sequence[EpisodeEvidence],
    family_id: str,
) -> bool:
    selected = tuple(
        episode for episode in episodes if episode.scenario_family_id == family_id
    )
    return bool(selected) and all(
        episode.scenario_verdict is not None
        and episode.scenario_verdict.source
        is ScenarioVerdictSource.DETERMINISTIC_ADAPTER
        for episode in selected
    )


def _validate_judge_coverage(
    episodes: Sequence[EpisodeEvidence],
    outcomes: Sequence[PairwiseOutcome],
) -> None:
    catalog = {family.family_id: family for family in scenario_catalog()}
    expected: List[Tuple[str, str, str, str, int, QualityDimension]] = []
    for episode in episodes:
        family = catalog.get(episode.scenario_family_id)
        if family is None:
            raise ValueError(f"unknown scenario family: {episode.scenario_family_id}")
        if episode.scenario_version != family.version:
            raise ValueError(
                "episode scenario version mismatch: "
                f"family={family.family_id}, catalog={family.version}, "
                f"episode={episode.scenario_version}"
            )
        expected.extend(
            (
                episode.scenario_family_id,
                episode.scenario_version,
                episode.variant_id,
                episode.fixture_id,
                episode.seed,
                dimension,
            )
            for dimension in family.dimensions
        )
    actual = [
        (
            outcome.scenario_family_id,
            outcome.scenario_version,
            outcome.variant_id,
            outcome.fixture_id,
            outcome.seed,
            outcome.dimension,
        )
        for outcome in outcomes
    ]
    if Counter(actual) != Counter(expected):
        raise ValueError(
            "judge coverage does not match paired episodes: "
            f"expected={Counter(expected)}, actual={Counter(actual)}"
        )


def _validate_judge_calibration_identity(
    votes: Sequence[JudgeVote],
    calibration: Optional[JudgeCalibrationReport],
) -> None:
    if calibration is None or not votes:
        return
    identities = {(vote.judge_id, vote.judge_revision) for vote in votes}
    expected = {(calibration.judge_id, calibration.judge_revision)}
    if identities != expected:
        raise ValueError(
            "judge calibration does not match comparison votes: "
            f"expected={expected}, actual={identities}"
        )
    vote_rubrics = {vote.rubric_version for vote in votes}
    if not vote_rubrics.issubset(set(calibration.rubric_versions)):
        raise ValueError(
            "judge calibration does not cover comparison rubrics: "
            f"calibrated={set(calibration.rubric_versions)}, actual={vote_rubrics}"
        )


def _episode_map(
    episodes: Iterable[EpisodeEvidence],
    label: str,
) -> Mapping[Tuple[str, str, str, int], EpisodeEvidence]:
    result = {}
    for episode in episodes:
        if episode.pair_key in result:
            raise ValueError(f"duplicate {label} episode key: {episode.pair_key}")
        result[episode.pair_key] = episode
    return result


def _single_candidate_id(
    episodes: Sequence[EpisodeEvidence],
    label: str,
) -> str:
    candidate_ids = {episode.candidate_id for episode in episodes}
    if len(candidate_ids) != 1:
        raise ValueError(f"{label} episodes require exactly one candidate_id")
    return candidate_ids.pop()


def _single_candidate_spec_sha256(
    episodes: Sequence[EpisodeEvidence],
    label: str,
) -> str:
    digests = {episode.candidate_spec_sha256 for episode in episodes}
    if len(digests) != 1:
        raise ValueError(f"{label} episodes require exactly one CandidateSpec digest")
    return digests.pop()


def _family_consistency_at_k(
    episodes: Mapping[Tuple[str, str, str, int], EpisodeEvidence],
    values: Mapping[Tuple[str, str, str, int], bool],
    k: int,
) -> Optional[Mapping[str, float]]:
    groups: DefaultDict[Tuple[str, str, str], List[bool]] = defaultdict(list)
    for pair_key, episode in episodes.items():
        groups[
            (
                episode.scenario_family_id,
                episode.variant_id,
                episode.fixture_id,
            )
        ].append(values[pair_key])
    if not groups or any(len(group) < k for group in groups.values()):
        return None
    per_family: DefaultDict[str, List[float]] = defaultdict(list)
    for (family_id, _variant_id, _fixture_id), group in groups.items():
        successes = sum(group)
        per_family[family_id].append(
            comb(successes, k) / comb(len(group), k) if successes >= k else 0.0
        )
    return {
        family_id: float(fmean(probabilities))
        for family_id, probabilities in per_family.items()
    }


def _family_weighted_success_rate(
    ordered_keys: Sequence[Tuple[str, str, str, int]],
    values: Mapping[Tuple[str, str, str, int], bool],
) -> float:
    per_family: DefaultDict[str, List[bool]] = defaultdict(list)
    for key in ordered_keys:
        per_family[key[0]].append(values[key])
    return float(
        fmean(float(fmean(family_values)) for family_values in per_family.values())
    )


def _clustered_reliability_interval(
    ordered_keys: Sequence[Tuple[str, str, str, int]],
    baseline_values: Mapping[Tuple[str, str, str, int], bool],
    candidate_values: Mapping[Tuple[str, str, str, int], bool],
    *,
    bootstrap_samples: int,
    random_seed: int,
) -> tuple[float, float]:
    per_family: DefaultDict[str, List[int]] = defaultdict(list)
    for key in ordered_keys:
        per_family[key[0]].append(
            int(candidate_values[key]) - int(baseline_values[key])
        )
    family_means = {
        family_id: float(fmean(values)) for family_id, values in per_family.items()
    }
    return _clustered_family_mean_interval(
        family_means,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
    )


def _clustered_family_mean_interval(
    family_means: Mapping[str, float],
    *,
    bootstrap_samples: int,
    random_seed: int,
) -> tuple[float, float]:
    family_ids = sorted(family_means)
    generator = random.Random(random_seed)
    samples = sorted(
        float(
            fmean(
                family_means[generator.choice(family_ids)]
                for _family_index in family_ids
            )
        )
        for _ in range(bootstrap_samples)
    )
    return _quantile(samples, 0.025), _quantile(samples, 0.975)


def _bounded_check(metric: str, observed: float, limit: float) -> ResourceCheck:
    passed = observed <= limit
    return ResourceCheck(
        metric=metric,
        passed=passed,
        detail=f"observed={observed:.4f}, limit={limit:.4f}",
    )


def _optional_mean_check(
    metric: str,
    values: Sequence[Optional[int]],
    limit: float,
) -> ResourceCheck:
    if any(value is None for value in values):
        return ResourceCheck(
            metric=metric,
            valid=False,
            passed=False,
            detail="required resource metric is missing from one or more episodes",
        )
    observed = float(fmean(value for value in values if value is not None))
    return _bounded_check(metric, observed, limit)


def _quantile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = position - lower_index
    return values[lower_index] + (values[upper_index] - values[lower_index]) * fraction


__all__ = (
    "build_comparison_report",
    "check_resource_budget",
    "compare_reliability",
)
