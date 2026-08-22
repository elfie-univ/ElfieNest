from __future__ import annotations

from datetime import datetime, timezone

import pytest

from devtools.brain_eval.cli import _verify_episode_candidate
from devtools.brain_eval.contracts import (
    CandidateSpec,
    EpisodeEvidence,
    JudgePreference,
    JudgeVote,
    ModelExecutionEvidence,
    PresentationOrder,
    PromotionPolicy,
    QualityDimension,
    ResourceBudget,
    ResourceObservation,
    ScenarioVerdict,
    ScenarioVerdictSource,
    contract_sha256,
)
from devtools.brain_eval.evaluation import build_comparison_report, compare_reliability


def _episode(candidate_id: str) -> EpisodeEvidence:
    return EpisodeEvidence(
        candidate_id=candidate_id,
        candidate_spec_sha256="d" * 64,
        scenario_family_id="q3-memory-precision",
        scenario_version="1.0.0",
        variant_id="paraphrase-01",
        fixture_id="anchor-elfie",
        seed=1,
        execution_success=True,
        scenario_verdict=ScenarioVerdict(
            source=ScenarioVerdictSource.DETERMINISTIC_ADAPTER,
            evaluator_id="memory-adapter",
            evaluator_revision="v1",
            passed=True,
            evidence=("memory-fact-1",),
        ),
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


def _vote(order: PresentationOrder) -> JudgeVote:
    return JudgeVote(
        pair_id="pair-1",
        pair_evidence_sha256="f" * 64,
        scenario_family_id="q3-memory-precision",
        scenario_version="1.0.0",
        variant_id="paraphrase-01",
        fixture_id="wrong-fixture",
        seed=1,
        dimension=QualityDimension.MEMORY_RELATIONSHIPS,
        judge_id="judge-a",
        judge_revision="judge-v1",
        rubric_version="q3-rubric-v1",
        presentation_order=order,
        preference=JudgePreference.TIE,
        evidence=("output:0",),
        confidence=0.9,
    )


def test_judge_votes_must_belong_to_the_exact_episode_pair() -> None:
    with pytest.raises(
        ValueError,
        match="judge coverage does not match paired episodes",
    ):
        build_comparison_report(
            policy=_policy(),
            baseline_episodes=(_episode("baseline"),),
            candidate_episodes=(_episode("candidate"),),
            judge_votes=tuple(_vote(order) for order in PresentationOrder),
            judge_calibration=None,
            holdout_confirmation=None,
            constitutional_anchor_confirmation=None,
            bootstrap_samples=100,
        )


def test_pairing_rejects_different_scenario_or_verdict_revisions() -> None:
    baseline = _episode("baseline")
    wrong_scenario = _episode("candidate").model_copy(
        update={"scenario_version": "different-version"}
    )
    with pytest.raises(ValueError, match="episode protocol mismatch"):
        compare_reliability((baseline,), (wrong_scenario,), k=1)

    candidate = _episode("candidate")
    assert candidate.scenario_verdict is not None
    wrong_verdict = candidate.model_copy(
        update={
            "scenario_verdict": candidate.scenario_verdict.model_copy(
                update={"evaluator_revision": "v2"}
            )
        }
    )
    with pytest.raises(ValueError, match="scenario verdict evaluator mismatch"):
        compare_reliability((baseline,), (wrong_verdict,), k=1)


def test_episode_must_bind_the_exact_candidate_spec_content() -> None:
    spec = CandidateSpec(
        candidate_id="candidate",
        code_sha="1234567",
        model_provider="mock",
        model_id="elfie-mock",
        model_parameters_sha256="a" * 64,
        prompt_revision="prompt-v1",
        context_compiler_revision="compiler-v1",
        memory_policy_revision="memory-v1",
        tool_policy_revision="tools-v1",
        config_sha256="b" * 64,
        captured_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    episode = _episode("candidate").model_copy(
        update={
            "candidate_spec_sha256": contract_sha256(spec),
            "model_executions": (
                ModelExecutionEvidence(
                    food_key="mock",
                    provider="mock",
                    model_id="elfie-mock",
                    skipped=False,
                    degraded=False,
                ),
            ),
        }
    )

    _verify_episode_candidate((episode,), spec)

    changed_spec = spec.model_copy(update={"prompt_revision": "prompt-v2"})
    with pytest.raises(ValueError, match="CandidateSpec digest"):
        _verify_episode_candidate((episode,), changed_spec)
