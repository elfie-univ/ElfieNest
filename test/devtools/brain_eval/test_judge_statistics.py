from __future__ import annotations

from devtools.brain_eval.contracts import (
    JudgePreference,
    JudgeVote,
    PresentationOrder,
    QualityDimension,
)
from devtools.brain_eval.judge import consolidate_position_flips
from devtools.brain_eval.statistics import estimate_dimension_effect


def _vote(
    *,
    pair_id: str,
    family_id: str,
    order: PresentationOrder,
    preference: JudgePreference,
    judge_id: str = "judge-a",
) -> JudgeVote:
    return JudgeVote(
        pair_id=pair_id,
        pair_evidence_sha256="f" * 64,
        scenario_family_id=family_id,
        scenario_version="1.0.0",
        variant_id="default",
        fixture_id="anchor-elfie",
        seed=1,
        dimension=QualityDimension.MEMORY_RELATIONSHIPS,
        judge_id=judge_id,
        judge_revision="judge-v1",
        rubric_version="q3-rubric-v1",
        presentation_order=order,
        preference=preference,
        evidence=("reply:1",),
        confidence=0.9,
    )


def test_position_flip_requires_same_normalized_preference() -> None:
    votes = (
        _vote(
            pair_id="pair-1",
            family_id="q3-memory-use",
            order=PresentationOrder.BASELINE_FIRST,
            preference=JudgePreference.CANDIDATE,
        ),
        _vote(
            pair_id="pair-1",
            family_id="q3-memory-use",
            order=PresentationOrder.CANDIDATE_FIRST,
            preference=JudgePreference.CANDIDATE,
        ),
    )

    outcomes = consolidate_position_flips(votes)

    assert len(outcomes) == 1
    assert outcomes[0].valid is True
    assert outcomes[0].value == 1


def test_position_disagreement_is_invalid_not_a_tie() -> None:
    votes = (
        _vote(
            pair_id="pair-1",
            family_id="q3-memory-use",
            order=PresentationOrder.BASELINE_FIRST,
            preference=JudgePreference.CANDIDATE,
        ),
        _vote(
            pair_id="pair-1",
            family_id="q3-memory-use",
            order=PresentationOrder.CANDIDATE_FIRST,
            preference=JudgePreference.BASELINE,
        ),
    )

    outcomes = consolidate_position_flips(votes)

    assert outcomes[0].valid is False
    assert outcomes[0].value is None
    assert outcomes[0].invalid_reason == "position_flip_disagreement"


def test_position_flip_cannot_mix_fixture_judge_or_rubric_revisions() -> None:
    first = _vote(
        pair_id="pair-1",
        family_id="q3-memory-precision",
        order=PresentationOrder.BASELINE_FIRST,
        preference=JudgePreference.CANDIDATE,
    )
    second = _vote(
        pair_id="pair-1",
        family_id="q3-memory-precision",
        order=PresentationOrder.CANDIDATE_FIRST,
        preference=JudgePreference.CANDIDATE,
    ).model_copy(update={"fixture_id": "different-fixture"})

    outcome = consolidate_position_flips((first, second))[0]

    assert outcome.valid is False
    assert outcome.invalid_reason == "position_flip_metadata_mismatch"

    different_rubric = second.model_copy(
        update={"fixture_id": first.fixture_id, "rubric_version": "q3-rubric-v2"}
    )
    rubric_outcome = consolidate_position_flips((first, different_rubric))[0]

    assert rubric_outcome.valid is False
    assert rubric_outcome.invalid_reason == "position_flip_metadata_mismatch"


def test_cluster_bootstrap_uses_scenario_families_not_turns() -> None:
    votes = []
    for pair_id, family_id, preference in (
        ("pair-1", "family-a", JudgePreference.CANDIDATE),
        ("pair-2", "family-b", JudgePreference.CANDIDATE),
        ("pair-3", "family-c", JudgePreference.TIE),
        ("pair-4", "family-d", JudgePreference.CANDIDATE),
    ):
        votes.extend(
            (
                _vote(
                    pair_id=pair_id,
                    family_id=family_id,
                    order=PresentationOrder.BASELINE_FIRST,
                    preference=preference,
                ),
                _vote(
                    pair_id=pair_id,
                    family_id=family_id,
                    order=PresentationOrder.CANDIDATE_FIRST,
                    preference=preference,
                ),
            )
        )
    outcomes = consolidate_position_flips(tuple(votes))

    effect = estimate_dimension_effect(
        outcomes,
        QualityDimension.MEMORY_RELATIONSHIPS,
        bootstrap_samples=500,
        random_seed=17,
    )

    assert effect.valid is True
    assert effect.scenario_family_count == 4
    assert effect.pair_count == 4
    assert effect.net_advantage == 0.75
    assert effect.lower_bound is not None
    assert effect.upper_bound is not None
    assert effect.lower_bound <= effect.net_advantage <= effect.upper_bound


def test_each_scenario_family_has_equal_weight_even_with_more_variants() -> None:
    votes = []
    for index in range(9):
        votes.extend(
            (
                _vote(
                    pair_id=f"large-family-{index}",
                    family_id="family-large",
                    order=PresentationOrder.BASELINE_FIRST,
                    preference=JudgePreference.CANDIDATE,
                ),
                _vote(
                    pair_id=f"large-family-{index}",
                    family_id="family-large",
                    order=PresentationOrder.CANDIDATE_FIRST,
                    preference=JudgePreference.CANDIDATE,
                ),
            )
        )
    votes.extend(
        (
            _vote(
                pair_id="small-family",
                family_id="family-small",
                order=PresentationOrder.BASELINE_FIRST,
                preference=JudgePreference.BASELINE,
            ),
            _vote(
                pair_id="small-family",
                family_id="family-small",
                order=PresentationOrder.CANDIDATE_FIRST,
                preference=JudgePreference.BASELINE,
            ),
        )
    )

    effect = estimate_dimension_effect(
        consolidate_position_flips(tuple(votes)),
        QualityDimension.MEMORY_RELATIONSHIPS,
        bootstrap_samples=500,
        random_seed=17,
    )

    assert effect.net_advantage == 0.0
